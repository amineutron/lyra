"""
Lyra Core - Pipeline principal.

Orchestration complete du workflow RAG:
1. Detection type query (knowledge vs action)
2. RAG retrieval des specs MCP
3. EPHAISTOS pour analyse arguments
4. LYRA pour dialogue/clarification
5. HESTIA pour execution MCP
"""

from typing import Optional

from .config import RAGConfig
from .types import (
    QueryType,
    PipelineResult,
)
from .menus import (
    is_list_tools_query,
    process_tools_query_step1,
    handle_server_selection,
)
from .retrieval import Retriever
from .formatters import (
    enrich_description,
    enrich_optional_args,
    format_listing_result,
)
from .validation import (
    VM_TOOLS_NEED_EXISTING,
    VM_TOOLS_REQUIRE_VM_NAME,
    VM_TOOLS_REQUIRE_RUNNING,
    VM_TOOLS_SHOW_STATE,
    get_existing_vm_names,
    get_vm_state,
    validate_vm_existence,
)
from .workflows.context import WorkflowContext
from .workflows.vm_start import handle_vm_start_confirm
from .workflows.vm_stop import handle_vm_stop_choice
from .workflows.vm_snapshot import (
    handle_vm_snapshot_create_workflow,
    handle_vm_snapshot_list_workflow,
    handle_vm_snapshot_pending,
)
from .workflows.vm_clone import suggest_vm_name, handle_cow_choice, handle_vm_clone_workflow
from .workflows.vm_export import handle_vm_export_custom_workflow, handle_custom_export_step
from ..rag.session_memory import (
    SessionMemory, PendingAction, PendingChoice,
    CHOICE_VM_START_CONFIRM, CHOICE_SERVER_SELECTION, CHOICE_TOOL_DISAMBIGUATION,
    META_COW_CHOICE_PENDING, META_STOP_CHOICE_PENDING, META_CUSTOM_EXPORT_STEP,
)
from ..models.model_manager import ModelManager
from ..models.ephaistos import Ephaistos, EphaistosAnalysis
from ..models.lyra_voice import LyraVoice, LyraResponse
from ..models.intent_classifier import IntentClassifier, Intent
from ..hestia.executor import HestiaExecutor, ExecutionContext, ExecutionResult
from ..utils.toon import toon_encode_specs


class Pipeline:
    """Pipeline principal RAG.

    Workflow:
    1. Detection type query (knowledge vs action)
    2. Si knowledge -> RAG -> LYRA -> reponse directe
    3. Si action -> RAG -> EPHAISTOS -> analyse args
    4. Si args manquants -> LYRA -> question -> session pending
    5. Si args complets -> EPHAISTOS -> validation
    6. Si valide -> HESTIA -> execution MCP
    7. LYRA -> formatage resultat
    """

    def __init__(self, config: RAGConfig, tts_mode: bool = False):
        """Initialise le pipeline.

        Args:
            config: Configuration RAG
            tts_mode: Mode TTS (True = vocal court, False = texte detaille)
        """
        self.config = config
        self.tts_mode = tts_mode
        self._initialized = False

        # Composants (initialises lazily)
        self._retriever: Optional[Retriever] = None
        self._model_manager: Optional[ModelManager] = None
        self._ephaistos: Optional[Ephaistos] = None
        self._lyra: Optional[LyraVoice] = None
        self._intent_classifier: Optional[IntentClassifier] = None
        self._hestia: Optional[HestiaExecutor] = None
        self._session: Optional[SessionMemory] = None

    def initialize(self):
        """Initialise les composants du pipeline.

        RAG (SentenceTransformer + ChromaDB) et HESTIA (MCPManager) sont
        initialises en parallele — ils sont independants et peuvent demarrer
        simultanement. Gain typique : ~1-2s sur le demarrage interactif.
        """
        if self._initialized:
            return

        from concurrent.futures import ThreadPoolExecutor

        # Config HESTIA preparee ici (thread-safe, juste un dict)
        full_config = {
            "llm": self.config.llm,
            "mcp": self.config.mcp
        }
        notion_config = (
            {"token": self.config.notion.token,
             "database_id": self.config.notion.database_id}
            if self.config.notion.enabled else None
        )

        def _init_rag():
            self._retriever = Retriever(self.config)
            self._retriever.initialize()

        def _init_hestia():
            self._hestia = HestiaExecutor(
                config=full_config,
                notion_enabled=self.config.notion.enabled,
                notion_config=notion_config
            )

        # RAG + HESTIA en parallele (independants)
        with ThreadPoolExecutor(max_workers=2) as executor:
            f_rag = executor.submit(_init_rag)
            f_hestia = executor.submit(_init_hestia)
            f_rag.result()     # propager les exceptions eventuelles
            f_hestia.result()

        # Model Manager + EPHAISTOS + LYRA + Intent Classifier (sequentiel, rapide)
        self._model_manager = ModelManager(self.config)
        self._ephaistos = Ephaistos(self._model_manager)
        self._lyra = LyraVoice(self._model_manager, tts_mode=self.tts_mode)
        self._intent_classifier = IntentClassifier(self._model_manager)

        # Session memory
        self._session = SessionMemory(max_turns=self.config.session.max_turns)

        # Contexte partage pour les workflows metier
        self._ctx = WorkflowContext(
            hestia=self._hestia,
            lyra=self._lyra,
            ephaistos=self._ephaistos,
            session=self._session,
            tts_mode=self.tts_mode,
            prepare_execution=self._prepare_execution,
            route_query=self._route_query,
        )

        self._initialized = True

    def initialize_fast(self):
        """Init minimale pour le fast path one-shot.

        Initialise uniquement HESTIA + Session + LyraVoice.
        Skip SentenceTransformer + ChromaDB + IntentClassifier + Ephaistos.

        Utilise quand une regle statique a matche avant le demarrage complet.
        Gain typique : 2-4s vs initialize() complet.
        """
        if self._initialized:
            return

        # ModelManager + LYRA (confirm_action est template-based, pas de LLM)
        self._model_manager = ModelManager(self.config)
        self._lyra = LyraVoice(self._model_manager, tts_mode=self.tts_mode)
        # _ephaistos, _intent_classifier, _retriever restent None (non utilises)

        # HESTIA Executor (necessaire pour l'execution MCP)
        full_config = {
            "llm": self.config.llm,
            "mcp": self.config.mcp
        }
        self._hestia = HestiaExecutor(
            config=full_config,
            notion_enabled=self.config.notion.enabled,
            notion_config={
                "token": self.config.notion.token,
                "database_id": self.config.notion.database_id
            } if self.config.notion.enabled else None
        )

        # Session memory
        self._session = SessionMemory(max_turns=self.config.session.max_turns)

        # Contexte partage (lyra present, ephaistos None)
        self._ctx = WorkflowContext(
            hestia=self._hestia,
            lyra=self._lyra,
            ephaistos=self._ephaistos,
            session=self._session,
            tts_mode=self.tts_mode,
            prepare_execution=self._prepare_execution,
            route_query=self._route_query,
        )

        self._initialized = True

    def process_precomputed(self, query: str, analysis: "EphaistosAnalysis") -> PipelineResult:
        """Traite une requete avec une analyse pre-calculee (fast path one-shot).

        Skip IntentClassifier + RAG + EPHAISTOS.
        Utilise directement l'analyse issue des regles statiques.

        Args:
            query: Requete originale
            analysis: EphaistosAnalysis pre-calculee par rules.detect()

        Returns:
            PipelineResult pret pour confirmation/execution
        """
        if not self._initialized:
            self.initialize_fast()

        return self._process_action(query, precomputed_analysis=analysis)

    def _enrich_description(self, name: str, description: str, server: str) -> str:
        return enrich_description(name, description, server)


    def _handle_pending_choice(self, query: str) -> PipelineResult:
        """Traite une reponse a un choix en attente.

        Args:
            query: Reponse de l'utilisateur

        Returns:
            PipelineResult
        """
        pending = self._session.get_pending_choice()
        if not pending:
            return self.process(query)

        # Clear le choix en attente
        self._session.clear_pending_choice()

        # Auto-dispatch via handler si le workflow a fourni un callable
        if pending.handler is not None:
            return pending.handler(query, pending, self._ctx)

        if pending.choice_type == CHOICE_SERVER_SELECTION:
            return handle_server_selection(query, pending.options, self._ctx)

        if pending.choice_type == CHOICE_VM_START_CONFIRM:
            return handle_vm_start_confirm(query, pending, self._ctx)

        if pending.choice_type == CHOICE_TOOL_DISAMBIGUATION:
            return self._handle_tool_disambiguation(query, pending)

        # Type de choix inconnu, traiter normalement
        return self._route_query(query)

    def _route_query(self, query: str, callback: Optional[callable] = None) -> PipelineResult:
        """Route une requete vers le bon handler.

        Utilise l'IntentClassifier (agent LYRA) pour determiner l'intention:
        - demande → action MCP
        - info → question de connaissance
        - discussion → conversation generale

        Args:
            query: Requete utilisateur
            callback: Callback optionnel pour feedback progressif

        Returns:
            PipelineResult
        """
        # Cas special: requete de liste d'outils
        if is_list_tools_query(query):
            return process_tools_query_step1(query, self._ctx)

        # Classifier l'intention via l'agent LYRA
        if self._intent_classifier is not None:
            classification = self._intent_classifier.classify(query)

            # ACKNOWLEDGEMENT IMMÉDIAT (Nouveau !)
            if callback and self._lyra:
                ack = self._lyra.generate_acknowledgement(
                    intent=classification.intent,
                    query=query
                )
                if ack:
                    callback("acknowledgement", ack)

            if classification.intent == Intent.INFO:
                return self._process_knowledge(query)
            elif classification.intent == Intent.DISCUSSION:
                return self._process_discussion(query)
            else:  # Intent.DEMANDE
                return self._process_action(query)
        else:
            # Fallback: utiliser l'ancienne detection (pour tests)
            query_type = self._retriever.detect_query_type(query)
            if query_type == QueryType.KNOWLEDGE:
                return self._process_knowledge(query)
            else:
                return self._process_action(query)

    def _process_discussion(self, query: str) -> PipelineResult:
        """Traite une conversation generale.

        Args:
            query: Message de l'utilisateur

        Returns:
            PipelineResult avec la reponse conversationnelle
        """
        # Utiliser LYRA pour repondre naturellement
        response = self._lyra.chat(query)

        self._session.add_turn(
            user_input=query,
            assistant_response=response.text
        )

        return PipelineResult(
            response=response.text,
            query_type=QueryType.KNOWLEDGE  # Discussion = pas d'action
        )

    def _process_knowledge(self, query: str) -> PipelineResult:
        """Traite une question de connaissance.

        Args:
            query: Question utilisateur

        Returns:
            PipelineResult avec la reponse
        """
        # Recuperer le contexte RAG
        fused = self._retriever.retrieve(query)

        if not fused:
            response = self._lyra.answer_knowledge(
                question=query,
                context="Aucune information pertinente trouvee dans les specs MCP."
            )
        else:
            context = "\n\n".join([r.document for r in fused])
            response = self._lyra.answer_knowledge(
                question=query,
                context=context
            )

        # Enregistrer le tour
        self._session.add_turn(
            user_input=query,
            assistant_response=response.text
        )

        return PipelineResult(
            response=response.text,
            query_type=QueryType.KNOWLEDGE
        )

    def _get_existing_vm_names(self) -> list[str]:
        return get_existing_vm_names(self._hestia)

    def _get_vm_state(self, vm_name: str) -> dict:
        return get_vm_state(self._hestia, vm_name)

    @staticmethod
    def _rule_based_detect(query: str) -> Optional[EphaistosAnalysis]:
        """Detection par regles pour les cas ou RAG+EPHAISTOS echouent systematiquement."""
        from ..rules import detect
        return detect(query)

    @staticmethod
    def _enrich_optional_args(query: str, analysis: EphaistosAnalysis) -> EphaistosAnalysis:
        return enrich_optional_args(query, analysis)

    def _handle_tool_disambiguation(self, query: str, pending: "PendingChoice") -> PipelineResult:
        """Traite la reponse utilisateur a une question de disambiguation d'outil."""
        q = query.strip().lower()
        candidates = pending.metadata.get("candidates", [])
        original_query = pending.metadata.get("query", query)
        fused = pending.metadata.get("fused", [])

        # Annulation
        if q in ("n", "non", "annuler", "cancel", "no", "rien", "aucun"):
            response = "Action annulee."
            self._session.add_turn(user_input=query, assistant_response=response)
            return PipelineResult(response=response, query_type=QueryType.ACTION)

        # Parsing du choix numerique
        idx = -1
        try:
            idx = int(q) - 1
        except ValueError:
            for i, c in enumerate(candidates):
                if q in c["tool"].lower() or q in c["server"].lower():
                    idx = i
                    break

        if idx < 0 or idx >= len(candidates):
            response = f"Choix invalide. Tape 1-{len(candidates)} ou n pour annuler."
            self._session.add_turn(user_input=query, assistant_response=response)
            return PipelineResult(response=response, query_type=QueryType.ACTION)

        chosen_server = candidates[idx]["server"]
        # Filtrer les specs RAG au serveur choisi
        filtered_fused = [
            r for r in fused
            if (r.metadata or {}).get("server_name", "") == chosen_server
            or (r.metadata or {}).get("name", "").split(".")[0] == chosen_server
        ] or fused  # fallback: tout si rien ne matche

        return self._process_action(original_query, precomputed_specs=filtered_fused)

    def _process_action(self, query: str, precomputed_specs: Optional[list] = None,
                        precomputed_analysis: Optional["EphaistosAnalysis"] = None) -> PipelineResult:
        """Traite une demande d'action.

        Args:
            query: Requete utilisateur
            precomputed_specs: Specs RAG deja recuperees (pour pipeline Enhanced)
            precomputed_analysis: Analyse deja determinee (pour fast path regle)
                                  Si fourni, RAG + EPHAISTOS sont sautes.

        Returns:
            PipelineResult avec l'action/question
        """
        # --- Fast path : analyse pre-calculee (regle ou pipeline Enhanced) ---
        if precomputed_analysis is not None:
            analysis = precomputed_analysis
            fused = []
            specs = []
        else:
            # Recuperer les specs MCP pertinentes (ou utiliser celles pre-calculees)
            if precomputed_specs is not None:
                fused = precomputed_specs
            else:
                fused = self._retriever.retrieve(query)

            if not fused:
                response = "Je n'ai pas trouve d'outil correspondant a ta demande."
                self._session.add_turn(
                    user_input=query,
                    assistant_response=response
                )
                return PipelineResult(
                    response=response,
                    query_type=QueryType.ACTION,
                    error="Aucun outil trouve"
                )

            # Extraire les specs pour EPHAISTOS
            specs = [r.document for r in fused]

            # Detection regle avant EPHAISTOS
            analysis = self._rule_based_detect(query)
            if analysis is not None:
                analysis = Pipeline._enrich_optional_args(query, analysis)

        if analysis is None:
            # Encoder en TOON uniquement si le modele est >= 1B (0.5b ne comprend pas TOON)
            ephaistos_model = self.config.models.ephaistos.name
            use_toon = "0.5b" not in ephaistos_model
            specs_toon = toon_encode_specs(specs) if use_toon else None

            # Analyser avec EPHAISTOS
            analysis = self._ephaistos.analyze_with_retry(
                user_query=query,
                mcp_specs=specs,
                specs_toon=specs_toon
            )

        # Disambiguation: si EPHAISTOS est peu confiant et les top candidats sont de serveurs differents
        if fused and not analysis.no_match and analysis.confidence < 0.70:
            candidates = _extract_disambiguation_candidates(fused)
            if len(candidates) >= 2:
                question = _build_disambiguation_question(candidates)
                pending = PendingChoice(
                    choice_type=CHOICE_TOOL_DISAMBIGUATION,
                    options=[c["tool"] for c in candidates],
                    question=question,
                    metadata={"candidates": candidates, "query": query, "fused": fused},
                )
                self._session.set_pending_choice(pending)
                self._session.add_turn(user_input=query, assistant_response=question)
                return PipelineResult(response=question, query_type=QueryType.ACTION)

        # Sanitize: backup_status ne doit JAMAIS recevoir watch=True
        # Le mode watch fait boucler le MCP indefiniment (timeout 124)
        if analysis.tool and 'backup_status' in analysis.tool:
            analysis.arguments.pop('watch', None)

        # Post-traiter le nom de l'outil pour ajouter le préfixe serveur si manquant
        # EPHAISTOS retourne "vm_clone" mais on veut "fedora.vm_clone"
        if analysis.tool and '.' not in analysis.tool:
            # Chercher le nom complet dans les metadata des specs RAG
            for r in fused:
                meta = r.metadata if isinstance(r.metadata, dict) else {}
                tool_name = meta.get('name', '')
                # Vérifier si le nom court correspond (ex: "vm_clone" dans "fedora.vm_clone")
                if tool_name.endswith('.' + analysis.tool) or tool_name == analysis.tool:
                    # Utiliser le nom complet
                    analysis.tool = tool_name
                    break

        # Cas 1: Aucun outil ne correspond
        if analysis.no_match:
            response = "Je n'ai pas compris quelle action tu veux faire."
            self._session.add_turn(
                user_input=query,
                assistant_response=response
            )
            return PipelineResult(
                response=response,
                query_type=QueryType.ACTION,
                error="Pas d'outil correspondant"
            )

        # Workflow special pour vm_export mode custom (interactif multi-tours)
        if analysis.tool and analysis.tool in ("vm_export", "fedora.vm_export"):
            if analysis.arguments.get("mode") == "custom":
                vm_name = analysis.arguments.get("vm_name", "")
                return handle_vm_export_custom_workflow(vm_name, query, self._ctx)

        # Workflow special pour vm_clone (PAS vm_clone_system)
        if analysis.tool and analysis.tool in ("vm_clone", "fedora.vm_clone"):
            return handle_vm_clone_workflow(query, analysis, self._ctx)

        # Workflow special pour vm_snapshot
        if analysis.tool and "vm_snapshot" in analysis.tool:
            action = analysis.arguments.get("action")
            vm_name = analysis.arguments.get("vm_name")

            # Workflow list sans VM: lister les VMs disponibles (proactif)
            if action == "list" and not vm_name:
                return handle_vm_snapshot_list_workflow(query, analysis, self._ctx)

            # Workflow creation avec nom par defaut
            if action == "create":
                # Si vm_name manquant, forcer clarification
                if not vm_name:
                    if "vm_name" not in analysis.missing_args:
                        analysis.missing_args.append("vm_name")
                else:
                    # Si vm_name present mais snapshot_name absent
                    snapshot_name = analysis.arguments.get("snapshot_name")
                    if not snapshot_name:
                        return handle_vm_snapshot_create_workflow(query, analysis, self._ctx)

            # Autres actions (restore, delete, etc.) sans VM: forcer clarification
            if not vm_name and "vm_name" not in analysis.missing_args:
                analysis.missing_args.append("vm_name")

        # Cas 2: Arguments manquants -> clarification
        if analysis.needs_clarification:
            # Generer la question via LYRA
            lyra_response = self._lyra.ask_clarification(
                missing_args=analysis.missing_args,
                tool_name=analysis.tool,
                use_llm=True,
                known_args=analysis.arguments
            )

            # Sauvegarder l'action en attente
            self._session.set_pending_action(
                tool_name=analysis.tool,
                known_args=analysis.arguments,
                missing_args=analysis.missing_args,
                clarification_question=lyra_response.text
            )

            # Enregistrer le tour
            self._session.add_turn(
                user_input=query,
                assistant_response=lyra_response.text
            )

            _src = "rule" if (analysis.reasoning and analysis.reasoning.startswith("rule:")) else "ephaistos"
            return PipelineResult(
                response=lyra_response.text,
                query_type=QueryType.ACTION,
                tool_call={"name": analysis.tool, "arguments": analysis.arguments},
                pending_args=analysis.missing_args,
                analysis_meta={"source": _src, "confidence": analysis.confidence,
                               "reasoning": analysis.reasoning or ""}
            )

        # Cas 3: Validation du nom de VM avant execution
        vm_error = self._validate_vm_existence(analysis, query)
        if vm_error is not None:
            return vm_error

        return self._prepare_execution(analysis, query)

    # Constantes importees depuis validation.py
    _VM_TOOLS_NEED_EXISTING = VM_TOOLS_NEED_EXISTING
    _VM_TOOLS_REQUIRE_VM_NAME = VM_TOOLS_REQUIRE_VM_NAME
    _VM_TOOLS_REQUIRE_RUNNING = VM_TOOLS_REQUIRE_RUNNING
    _VM_TOOLS_SHOW_STATE = VM_TOOLS_SHOW_STATE

    def _validate_vm_existence(
        self,
        analysis: "EphaistosAnalysis",
        query: str
    ) -> Optional["PipelineResult"]:
        return validate_vm_existence(self._hestia, self._session, analysis, query)

    def _prepare_execution(
        self,
        analysis: EphaistosAnalysis,
        original_query: str
    ) -> PipelineResult:
        """Prepare l'execution d'une action.

        Args:
            analysis: Analyse EPHAISTOS complete
            original_query: Requete originale

        Returns:
            PipelineResult pret pour execution
        """
        tool_call = {
            "name": analysis.tool,
            "arguments": analysis.arguments
        }
        _analysis_src = "rule" if (analysis.reasoning and analysis.reasoning.startswith("rule:")) else "ephaistos"
        _analysis_meta = {"source": _analysis_src, "confidence": analysis.confidence,
                          "reasoning": analysis.reasoning or ""}

        # Message de confirmation special pour vm_clone
        if analysis.tool and "vm_clone" in analysis.tool:
            source_vm = analysis.arguments.get("source_vm") or analysis.arguments.get("source_vm_name")
            new_vm_name = analysis.arguments.get("new_vm_name")

            confirm_msg = (
                "📋 Recapitulatif du clonage:\n\n"
                f"  🔹 VM source     : **{source_vm}**\n"
                f"  🔸 VM destination: **{new_vm_name}**\n\n"
                "Je clone cette VM?"
            )
        else:
            # Generer le message de confirmation via LYRA pour les autres outils
            confirm_msg = self._lyra.confirm_action(
                tool_name=analysis.tool,
                arguments=analysis.arguments
            )

            # Enrichir avec l'etat courant de la VM si applicable
            tool_short = analysis.tool.split(".")[-1] if analysis.tool else ""
            if tool_short in self._VM_TOOLS_SHOW_STATE:
                vm_name = analysis.arguments.get("vm_name")
                if vm_name:
                    state = self._get_vm_state(vm_name)
                    state_label = "en cours" if state["running"] else "arretee"
                    ip_info = f" | IP: {state['ip']}" if state.get("ip") else ""
                    confirm_msg = f"[{vm_name} : {state_label}{ip_info}]\n\n{confirm_msg}"

        # Enregistrer le tour
        self._session.add_turn(
            user_input=original_query,
            assistant_response=confirm_msg,
            tool_call=tool_call
        )

        return PipelineResult(
            response=confirm_msg,
            query_type=QueryType.ACTION,
            tool_call=tool_call,
            executed=False,  # Pas encore execute, attend confirmation
            analysis_meta=_analysis_meta
        )

    def _process_pending_action(self, query: str) -> PipelineResult:
        """Traite une reponse a une clarification en attente.

        Args:
            query: Reponse de l'utilisateur

        Returns:
            PipelineResult
        """
        pending = self._session.get_pending_action()
        if not pending:
            # Pas d'action en attente, traiter normalement
            return self._process_action(query)

        # Cas special: open_app sans ecran -> extraire l'ecran de la reponse utilisateur
        if pending.tool_name == "screen-manager.open_app" and "screen" in pending.missing_args:
            from ..rules.screen_manager import _extract_screen_dest
            from ..rules.base import normalize
            q = normalize(query)
            screen = _extract_screen_dest(q)
            if not screen:
                # Essayer d'extraire depuis la reponse libre ("le 2e", "gauche", "tele"...)
                import re as _re
                m = _re.search(
                    r'\b(?:ecran|moniteur|display|tele(?:vision)?|tv|'
                    r'gauche|droite|milieu|principal|secondaire|'
                    r'premier|deuxieme|troisieme|1er|2e|2eme|3e|3eme|\d+)\b', q
                )
                if m:
                    screen = m.group(0)
            if screen:
                args = dict(pending.known_args)
                args["screen"] = screen
                updated = EphaistosAnalysis(
                    tool="screen-manager.open_app",
                    arguments=args,
                    missing_args=[],
                    confidence=0.93,
                    reasoning="screen extrait de la reponse utilisateur",
                    raw_response=""
                )
                return self._prepare_execution(updated, query)
            else:
                # Toujours pas d'ecran: reposer la question
                question = "Sur quel ecran ? (ex: gauche, droite, 2e ecran, tele...)"
                self._session.set_pending_action(
                    tool_name="screen-manager.open_app",
                    known_args=pending.known_args,
                    missing_args=["screen"],
                    clarification_question=question
                )
                self._session.add_turn(user_input=query, assistant_response=question)
                return PipelineResult(response=question, query_type=QueryType.ACTION,
                                      pending_args=["screen"])

        # Cas spécial: workflow vm_export mode custom (multi-tours)
        if pending.known_args.get(META_CUSTOM_EXPORT_STEP) is not None:
            return handle_custom_export_step(query, pending, self._ctx)

        # Cas spécial: choix COW vs copie complete pour clone
        if pending.known_args.get(META_COW_CHOICE_PENDING):
            return handle_cow_choice(query, pending, self._ctx)

        # Cas spécial: choix arrêt VM pour clone
        if pending.known_args.get(META_STOP_CHOICE_PENDING):
            return handle_vm_stop_choice(query, pending, self._ctx)

        # Cas spécial: snapshot avec reponse par defaut
        if pending.tool_name and "vm_snapshot" in pending.tool_name:
            result = handle_vm_snapshot_pending(query, pending, self._ctx)
            if result is not None:
                return result

        # Extraire les nouveaux arguments avec EPHAISTOS
        if self._ephaistos is None:
            # fast-path init ne charge pas EPHAISTOS — initialiser maintenant
            self.initialize()

        partial_analysis = EphaistosAnalysis(
            tool=pending.tool_name,
            arguments={**pending.known_args},
            missing_args=pending.missing_args,
            confidence=0.8,
            reasoning="Action en attente",
            raw_response=""
        )

        updated_analysis = self._ephaistos.extract_missing_args(
            analysis=partial_analysis,
            user_response=query
        )

        # Workflow special pour vm_clone: valider que le nom n'existe pas ET vérifier l'état de la VM
        if updated_analysis.tool and "vm_clone" in updated_analysis.tool:
            # Si on a maintenant new_vm_name, valider
            if "new_vm_name" in updated_analysis.arguments and "new_vm_name" not in updated_analysis.missing_args:
                new_vm_name = updated_analysis.arguments["new_vm_name"]
                source_vm = updated_analysis.arguments.get("source_vm") or updated_analysis.arguments.get("source_vm_name")
                existing_vms = self._get_existing_vm_names()

                # Verifier si le nom existe deja
                if new_vm_name in existing_vms:
                    suggested_name = suggest_vm_name(existing_vms, source_vm)

                    question = f"Le nom '{new_vm_name}' existe deja!\n\nProposition: {suggested_name}\n\nQuel nom veux-tu utiliser ?"

                    # Remettre new_vm_name en missing
                    self._session.set_pending_action(
                        tool_name=updated_analysis.tool,
                        known_args={"source_vm": source_vm},
                        missing_args=["new_vm_name"],
                        clarification_question=question
                    )

                    self._session.add_turn(
                        user_input=query,
                        assistant_response=question
                    )

                    return PipelineResult(
                        response=question,
                        query_type=QueryType.ACTION,
                        tool_call={"name": updated_analysis.tool, "arguments": {"source_vm": source_vm}},
                        pending_args=["new_vm_name"]
                    )

                # Vérifier l'état de la VM source (running ou arrêtée)
                vm_state = self._get_vm_state(source_vm)

                if vm_state.get("running"):
                    # La VM est en cours d'exécution, proposer de l'arrêter
                    vm_intro = f"📋 VMs existantes: {', '.join(existing_vms)}\n\n"

                    question = (
                        vm_intro +
                        f"⚠️  La VM **{source_vm}** est en cours d'exécution!\n\n"
                        f"Pour cloner une VM, elle doit être arrêtée.\n\n"
                        f"💡 Options:\n"
                        f"  1. **Arrêter** temporairement {source_vm}, cloner, puis redémarrer\n"
                        f"  2. **Arrêter** {source_vm} et cloner (sans redémarrage)\n"
                        f"  3. **Annuler** le clonage\n\n"
                        f"Ton choix ? (1/2/3)"
                    )

                    # Sauvegarder le contexte avec un flag spécial
                    self._session.set_pending_action(
                        tool_name=updated_analysis.tool,
                        known_args={
                            "source_vm": source_vm,
                            "new_vm_name": new_vm_name,
                            "_vm_running": True,
                            META_STOP_CHOICE_PENDING: True
                        },
                        missing_args=[],
                        clarification_question=question
                    )

                    self._session.add_turn(
                        user_input=query,
                        assistant_response=question
                    )

                    return PipelineResult(
                        response=question,
                        query_type=QueryType.ACTION,
                        tool_call={"name": updated_analysis.tool, "arguments": {"source_vm": source_vm, "new_vm_name": new_vm_name}},
                        pending_args=["_user_choice"]  # Attend le choix 1/2/3
                    )

        # Workflow special pour vm_snapshot create avec nom par defaut
        if updated_analysis.tool and "vm_snapshot" in updated_analysis.tool:
            if updated_analysis.arguments.get("action") == "create":
                # Si snapshot_name vient d'etre fourni
                if "snapshot_name" in updated_analysis.arguments and "snapshot_name" not in updated_analysis.missing_args:
                    snapshot_name = updated_analysis.arguments["snapshot_name"]
                    vm_name = updated_analysis.arguments.get("vm_name")
                    default_name = pending.known_args.get("_default_snapshot_name")

                    # Cas 1: Reponse vide ou "ok"/"default" → utiliser le nom par defaut
                    if default_name and query.strip().lower() in ("", "ok", "oui", "d'accord", "default", "par défaut", "par defaut"):
                        updated_analysis.arguments["snapshot_name"] = default_name
                        snapshot_name = default_name

                    # Cas 2: Valider que snapshot_name != vm_name (eviter confusion)
                    elif snapshot_name == vm_name:
                        import datetime
                        # Auto-suffixer avec timestamp
                        timestamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
                        new_snapshot_name = f"{vm_name}-snap-{timestamp}"
                        updated_analysis.arguments["snapshot_name"] = new_snapshot_name

                        # Afficher warning (sera visible dans le recapitulatif)
                        print()
                        print(self._lyra._get_colored_text("⚠️  Le nom du snapshot ne peut pas être identique à la VM.", "yellow"))
                        print(self._lyra._get_colored_text(f"Nom modifié automatiquement: {new_snapshot_name}", "cyan"))
                        print()

        # Si encore des args manquants
        if updated_analysis.needs_clarification:
            # Mettre a jour l'action en attente
            self._session.set_pending_action(
                tool_name=updated_analysis.tool,
                known_args=updated_analysis.arguments,
                missing_args=updated_analysis.missing_args,
                clarification_question=""
            )

            # Generer nouvelle question
            lyra_response = self._lyra.ask_clarification(
                missing_args=updated_analysis.missing_args,
                tool_name=updated_analysis.tool,
                use_llm=True,
                known_args=updated_analysis.arguments
            )

            self._session.add_turn(
                user_input=query,
                assistant_response=lyra_response.text
            )

            return PipelineResult(
                response=lyra_response.text,
                query_type=QueryType.ACTION,
                tool_call={"name": updated_analysis.tool, "arguments": updated_analysis.arguments},
                pending_args=updated_analysis.missing_args
            )

        # Arguments complets -> clear pending et preparer execution
        self._session.clear_pending_action()
        return self._prepare_execution(updated_analysis, query)

    def process(self, query: str, callback: Optional[callable] = None) -> PipelineResult:
        """Traite une requete utilisateur.

        Args:
            query: Requete en francais
            callback: Fonction callback optionnelle pour feedback progressif.
                     Signature: callback(step: str, message: str)
                     Steps possibles: "acknowledgement", "progress", "result"

        Returns:
            PipelineResult avec la reponse
        """
        if not self._initialized:
            self.initialize()

        # Verifier s'il y a un choix en attente (priorite max)
        if self._session.get_pending_choice():
            return self._handle_pending_choice(query)

        # Verifier s'il y a une action en attente
        if self._session.get_pending_action():
            return self._process_pending_action(query)

        # Router vers le bon handler (avec callback)
        return self._route_query(query, callback=callback)

    # Outils de listing qui doivent retourner le resultat formate (pas de resume LYRA)
    LISTING_TOOLS = [
        "get_all_scenes", "get_all_lights", "get_all_groups",
        "list_apps",
        "vm_status", "backup_list", "backup_status",
        "get_light", "get_group", "find_light_by_name",
        "list_screens",  # screen-manager
    ]

    def _is_listing_tool(self, tool_name: str, arguments: dict = None) -> bool:
        """Verifie si un outil est un outil de listing.

        Args:
            tool_name: Nom de l'outil
            arguments: Arguments de l'outil (optionnel)

        Returns:
            True si c'est un outil de listing
        """
        # Extraire le nom sans prefixe serveur
        short_name = tool_name.split(".")[-1] if "." in tool_name else tool_name

        # Cas special: vm_snapshot avec action=list
        if short_name == "vm_snapshot" and arguments:
            return arguments.get("action") == "list"

        return short_name in self.LISTING_TOOLS

    def _format_listing_result(self, tool_name: str, content: str) -> str:
        return format_listing_result(tool_name, content)

    def execute_action(
        self,
        tool_name: str,
        arguments: dict,
        user_query: str = "",
        skip_lyra_format: bool = False
    ) -> PipelineResult:
        """Execute une action MCP via HESTIA.

        Appelee apres confirmation utilisateur.

        Args:
            tool_name: Nom de l'outil MCP
            arguments: Arguments de l'outil
            user_query: Requete originale (pour logging)

        Returns:
            PipelineResult avec le resultat
        """
        if not self._initialized:
            self.initialize()

        # Creer le contexte d'execution
        context = ExecutionContext(
            user_query=user_query,
            tool_name=tool_name,
            arguments=arguments
        )

        # Executer via HESTIA
        result = self._hestia.execute(
            tool_name=tool_name,
            arguments=arguments,
            context=context
        )

        # Pour les outils de listing, formater lisiblement
        # Pour les outils tracking, retourner le contenu brut directement (pas de LLM)
        # En fast path (skip_lyra_format=True) : contenu brut, pas d'appel LLM
        # Pour les autres, formater via LYRA
        if result.success:
            if skip_lyra_format or tool_name.startswith("tracking.") or tool_name == "open_tracking_ui":
                lyra_response = LyraResponse(
                    text=result.content,
                    mentions_ephaistos=False,
                    mentions_hestia=False
                )
            elif self._is_listing_tool(tool_name, arguments):
                # Formatage lisible pour les listings
                formatted = self._format_listing_result(tool_name, result.content)
                lyra_response = LyraResponse(
                    text=formatted,
                    mentions_ephaistos=False,
                    mentions_hestia=False
                )
            else:
                lyra_response = self._lyra.format_result(
                    tool_name=tool_name,
                    result=result.content,
                    success=True
                )
        else:
            if skip_lyra_format:
                lyra_response = LyraResponse(
                    text=result.error or "Erreur lors de l'execution.",
                    mentions_ephaistos=False,
                    mentions_hestia=False
                )
            else:
                lyra_response = self._lyra.format_error(
                    tool_name=tool_name,
                    error=result.error or "Erreur inconnue"
                )

        # Enregistrer le tour
        self._session.add_turn(
            user_input=f"[Execution] {tool_name}",
            assistant_response=lyra_response.text,
            tool_call={"name": tool_name, "arguments": arguments},
            tool_result=result.content if result.success else result.error
        )

        return PipelineResult(
            response=lyra_response.text,
            query_type=QueryType.ACTION,
            tool_call={"name": tool_name, "arguments": arguments},
            executed=True,
            execution_result=result,
            error=result.error if not result.success else None
        )

    def process_with_context(
        self,
        query: str,
        pending_action: Optional[dict] = None
    ) -> PipelineResult:
        """Traite une requete avec contexte d'action en attente.

        Args:
            query: Requete utilisateur
            pending_action: Action en attente de clarification

        Returns:
            PipelineResult
        """
        # Si pending_action fourni, le restaurer dans la session
        if pending_action:
            self._session.set_pending_action(
                tool_name=pending_action.get("tool_name", ""),
                known_args=pending_action.get("known_args", {}),
                missing_args=pending_action.get("missing_args", []),
                clarification_question=pending_action.get("question", "")
            )

        return self.process(query)

    def get_session_history(self) -> list:
        """Retourne l'historique de session."""
        if self._session is None:
            return []
        return self._session.get_history()

    def clear_session(self):
        """Efface la session courante."""
        if self._session is not None:
            self._session.clear()

    def get_pending_action(self) -> Optional[PendingAction]:
        """Retourne l'action en attente."""
        if self._session is None:
            return None
        return self._session.get_pending_action()

    def detect_query_type(self, query: str) -> QueryType:
        """Proxy vers Retriever.detect_query_type (compatibilite tests)."""
        from .retrieval import Retriever
        retriever = Retriever(self.config)
        return retriever.detect_query_type(query)

    def is_dangerous_action(self, tool_name: str) -> bool:
        """Verifie si une action est dangereuse."""
        if not self._hestia:
            return False
        return self._hestia.is_dangerous_tool(tool_name)

    def get_metrics(self) -> dict:
        """Retourne les metriques du pipeline."""
        metrics = {}

        if self._model_manager is not None:
            metrics["models"] = self._model_manager.get_stats()

        if self._hestia is not None:
            metrics["hestia"] = self._hestia.get_metrics()

        if self._session is not None:
            metrics["session"] = {
                "turns": len(self._session),
                "has_pending": self._session.get_pending_action() is not None
            }

        return metrics

    def close(self):
        """Ferme les connexions."""
        if self._hestia:
            self._hestia.close()


# ---------------------------------------------------------------------------
# Helpers disambiguation
# ---------------------------------------------------------------------------

def _extract_disambiguation_candidates(fused: list) -> list[dict]:
    """Extrait les top candidats de disambiguation (un par serveur)."""
    candidates = []
    seen_servers: set[str] = set()
    for r in fused[:8]:
        meta = r.metadata if isinstance(r.metadata, dict) else {}
        tool_name = meta.get("name", "")
        if not tool_name:
            continue
        server = meta.get("server_name", "")
        if not server and "." in tool_name:
            server = tool_name.split(".")[0]
        if server not in seen_servers:
            seen_servers.add(server)
            desc = (meta.get("description", "") or "").strip()
            candidates.append({
                "tool": tool_name,
                "server": server,
                "description": desc[:70],
            })
        if len(candidates) >= 4:
            break
    return candidates


def _build_disambiguation_question(candidates: list[dict]) -> str:
    """Construit la question de disambiguation multi-choix."""
    lines = ["Je ne suis pas sur. Lequel tu veux ?", ""]
    tool_w = max((len(c["tool"]) for c in candidates), default=10) + 2
    srv_w = max((len(c["server"]) for c in candidates), default=6) + 2
    for i, c in enumerate(candidates, 1):
        tool_col = c["tool"].ljust(tool_w)
        srv_col = f"[{c['server']}]".ljust(srv_w + 2)
        desc = c["description"] or ""
        lines.append(f"  {i}. {tool_col} {srv_col}  {desc}")
    n = len(candidates)
    options = "/".join(str(i) for i in range(1, n + 1))
    lines.append(f"\n[{options}/n]  (n = annuler)")
    return "\n".join(lines)
