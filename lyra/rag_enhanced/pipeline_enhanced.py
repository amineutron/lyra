"""
Pipeline Enhanced - Intégration complète RAG Enhanced.

SESSION 7 (P6.1)

Enrichit le pipeline V2 avec :
- SlangNormalizer : Normalisation anglicismes
- SynonymExpander : Expansion synonymes
- ContextInjector : Injection contexte session
- RAG3Tier : 3 collections ChromaDB (optionnel)
- ConfidenceCascader : Seuils confiance
- FeedbackLoop : Apprentissage continu
"""

import time
from typing import Optional, Callable
from dataclasses import dataclass, field

from ..core.pipeline import Pipeline, PipelineResult, QueryType
from ..core.config import RAGConfig

# Imports RAG Enhanced
from .config import RAGEnhancedConfig
from .slang_normalizer import get_default_normalizer
from .synonym_expander import get_synonym_expander
from .context_injector import get_context_injector
from .rag_3tier import get_rag_3tier
from .confidence_cascader import get_confidence_cascader, CascadeAction
from .feedback_loop import get_feedback_loop


@dataclass
class EnhancedPipelineResult(PipelineResult):
    """Résultat du pipeline enhanced avec métriques."""

    # Queries intermédiaires
    normalized_query: Optional[str] = None
    expanded_query: Optional[str] = None
    enriched_query: Optional[str] = None  # Query avec contexte injecté

    # RAG source
    rag_source: Optional[str] = None  # "registry", "capabilities", "parameters", "v2_fallback"

    # Cascade
    cascade_action: Optional[str] = None  # "execute", "propose", "fallback"
    confidence_level: Optional[str] = None  # "high", "medium", "low" (M2)
    rag_score: Optional[float] = None
    should_inject_context: bool = False
    context_injected: bool = False  # True si contexte réellement injecté
    requires_confirmation: bool = False  # True si confirmation utilisateur requise

    # Feedback
    feedback_recorded: bool = False

    # Métriques (latency en ms)
    metrics: dict = field(default_factory=dict)


class EnhancedPipeline:
    """Pipeline Enhanced avec feature flags granulaires.
    
    Encapsule le Pipeline V2 et ajoute les composants RAG Enhanced.
    
    Workflow:
        USER QUERY
            ↓
        1. SlangNormalizer.normalize()        <1ms
            ↓
        2. SynonymExpander.expand()           <1ms
            ↓
        3. RAG3Tier.cascade_search() OU V2   ~20-30ms
            ↓
        4. ConfidenceCascader.cascade()       <2ms
            ├─→ HIGH (>0.85) → EXECUTE direct
            ├─→ MEDIUM (0.60-0.85) → ContextInjector.inject()  ~10ms
            └─→ LOW (<0.60) → FALLBACK
            ↓
        5. Pipeline V2 (EPHAISTOS, LYRA, HESTIA)
            ↓
        6. FeedbackLoop.record()              <2ms
            ↓
        RESULT
        
    Exemples:
        >>> pipeline = EnhancedPipeline(enabled=True)
        >>> pipeline.initialize()
        >>> result = pipeline.process_query("start preprod-09")
        >>> print(result.normalized_query)  # "démarre preprod-09"
    """
    
    def __init__(
        self,
        config: Optional[RAGConfig] = None,
        enhanced_config: Optional[RAGEnhancedConfig] = None,
        enabled: bool = True,
        tts_mode: bool = False
    ):
        """Initialise le pipeline enhanced.
        
        Args:
            config: Configuration RAG V2 (si None, chargé depuis config.yaml)
            enhanced_config: Configuration RAG Enhanced (si None, défauts)
            enabled: Master switch (False = V2 pur sans enrichissement)
            tts_mode: Mode TTS (vocal)
        """
        # Config
        if config is None:
            from pathlib import Path
            config = RAGConfig.from_yaml(Path("config.yaml"))
        
        self.config = config
        self.enhanced_config = enhanced_config or RAGEnhancedConfig()
        self.enabled = enabled
        self.tts_mode = tts_mode
        
        # Pipeline V2 sous-jacent
        self._pipeline_v2 = Pipeline(config=config, tts_mode=tts_mode)
        
        # Composants RAG Enhanced (lazy-loaded)
        self._slang_normalizer = None
        self._synonym_expander = None
        self._context_injector = None
        self._rag_3tier = None
        self._confidence_cascader = None
        self._feedback_loop = None
        
        self._initialized = False
    
    def initialize(self):
        """Initialise le pipeline et les composants."""
        if self._initialized:
            return
        
        # Initialiser V2
        self._pipeline_v2.initialize()
        
        # Initialiser composants RAG Enhanced si enabled
        if self.enabled:
            # Slang Normalizer
            if self.enhanced_config.slang_normalizer.enabled:
                self._slang_normalizer = get_default_normalizer()
            
            # Synonym Expander
            if self.enhanced_config.synonym_expander.enabled:
                self._synonym_expander = get_synonym_expander()
            
            # Context Injector
            if self.enhanced_config.context_injector.enabled:
                self._context_injector = get_context_injector()
            
            # RAG 3-Tier (optionnel, remplace semantic V2)
            if self.enhanced_config.rag_3tier.enabled:
                self._rag_3tier = get_rag_3tier()
                self._rag_3tier.initialize()
            
            # Confidence Cascader (utilise seuils du feedback_loop)
            if self.enhanced_config.feedback_loop.enabled:
                self._confidence_cascader = get_confidence_cascader()
                self._feedback_loop = get_feedback_loop()
        
        self._initialized = True

    def preload_models(self) -> None:
        """Precharge les modeles Ollama en VRAM (delegue au pipeline V2)."""
        self._pipeline_v2.preload_models()

    def initialize_fast(self):
        """Init minimale pour le fast path one-shot.

        Initialise uniquement le pipeline V2 en mode fast (HESTIA + Session + LyraVoice)
        et le slang normalizer (pure Python, <1ms).
        Skip SentenceTransformer + ChromaDB + LLMs.
        """
        if self._initialized:
            return
        self._pipeline_v2.initialize_fast()
        # Slang normalizer : pure Python, aucune dep lourde
        if self.enabled and self.enhanced_config.slang_normalizer.enabled:
            self._slang_normalizer = get_default_normalizer()
        self._initialized = True

    def process_precomputed(self, query: str, analysis) -> "EnhancedPipelineResult":
        """Fast path : traite une requete avec analyse pre-calculee.

        Delegue au pipeline V2 en bypassing IntentClassifier + RAG + EPHAISTOS.

        Args:
            query: Requete originale (ou normalisee)
            analysis: EphaistosAnalysis issue de rules.detect()

        Returns:
            PipelineResult (compatible EnhancedPipelineResult)
        """
        if not self._initialized:
            self.initialize_fast()
        return self._pipeline_v2.process_precomputed(query, analysis)

    def process(
        self,
        user_input: str,
        callback=None,
        session_id: str = "default",
        rag_step_callback: Optional[Callable[[str, dict], None]] = None
    ) -> EnhancedPipelineResult:
        """Traite une requête utilisateur (compatibilité Pipeline V2).

        Méthode wrapper pour compatibilité avec l'interface Pipeline V2.
        Délègue à process_query() pour la logique enhanced.

        Args:
            user_input: Requête utilisateur
            callback: Callback pour opérations async (passé au pipeline V2)
            session_id: ID de session (défaut: "default")
            rag_step_callback: Callback verbose RAG 3-tier (M1).
                               Signature: rag_step_callback(step: str, data: dict)

        Returns:
            EnhancedPipelineResult: Résultat avec métriques
        """
        # Stocker le callback pour qu'il soit accessible par HESTIA
        if callback:
            self._pipeline_v2._callback = callback

        # Déléguer à process_query dans le scope de la session demandée
        # (active le session_id, auparavant paramètre mort)
        with self._pipeline_v2.session_scope(session_id):
            return self.process_query(user_input, session_id, rag_step_callback=rag_step_callback)

    def process_query(
        self,
        query: str,
        session_id: str = "default",
        rag_step_callback: Optional[Callable[[str, dict], None]] = None
    ) -> EnhancedPipelineResult:
        """Traite une requête utilisateur.

        Args:
            query: Requête utilisateur
            session_id: ID de session (pour contexte)
            rag_step_callback: Callback verbose RAG 3-tier (M1).
                               Appelé à chaque étape du RAG 3-tier avec (step, data).

        Returns:
            EnhancedPipelineResult: Résultat avec métriques
        """
        if not self._initialized:
            self.initialize()
        
        start_time = time.time()
        metrics = {}

        # === BYPASS : Réponse à une question en attente (pending_args) ===
        # Si le pipeline V2 attend une réponse (pending_action / pending_choice),
        # on ne passe PAS par slang/synonym normalization.
        # Le V2 gère lui-même la réponse (nom de VM, choix, etc.).
        has_pending = False
        if self._pipeline_v2._session is not None:
            has_pending = (
                self._pipeline_v2._session.get_pending_action() is not None
                or self._pipeline_v2._session.get_pending_choice() is not None
            )
        if has_pending:
            t0 = time.time()
            result_v2 = self._pipeline_v2.process(query)
            metrics['v2_pipeline_latency_ms'] = (time.time() - t0) * 1000
            metrics['total_latency_ms'] = (time.time() - start_time) * 1000
            return self._wrap_v2_result(result_v2, query, metrics)

        # Si enhanced disabled, fallback V2 pur
        if not self.enabled:
            result_v2 = self._pipeline_v2.process(query)
            return self._wrap_v2_result(result_v2, query, metrics)

        # === ÉTAPE 1 : Slang Normalizer ===
        normalized_query = query
        if self._slang_normalizer:
            t0 = time.time()
            normalized_query = self._slang_normalizer.normalize(query)
            metrics['slang_latency_ms'] = (time.time() - t0) * 1000
        
        # === ÉTAPE 2 : Synonym Expander ===
        expanded_query = normalized_query
        if self._synonym_expander:
            t0 = time.time()
            expanded_query = self._synonym_expander.expand(normalized_query)
            metrics['synonym_latency_ms'] = (time.time() - t0) * 1000

        # === ÉTAPE 2.5 : Fast path - règle statique avant RAG ===
        # Si une règle matche, on saute le RAG 3-tier entièrement (plus rapide,
        # pas de step messages erronés sur le mauvais serveur/outil)
        precheck_analysis = Pipeline._rule_based_detect(normalized_query)
        if precheck_analysis is not None:
            precheck_analysis = Pipeline._enrich_optional_args(normalized_query, precheck_analysis)
            if rag_step_callback:
                tool_short = precheck_analysis.tool.split(".")[-1].replace("_", " ")
                server = precheck_analysis.tool.split(".")[0].upper() if "." in precheck_analysis.tool else "?"
                rag_step_callback("rule_matched", {
                    "tool": precheck_analysis.tool,
                    "tool_short": tool_short,
                    "server": server,
                    "score": 1.0,
                })
            # Intent classifier (pour demande/info/discussion)
            t0 = time.time()
            if self._pipeline_v2._intent_classifier is not None:
                classification = self._pipeline_v2._intent_classifier.classify(normalized_query)
                if classification.intent.value == "discussion":
                    result_v2 = self._pipeline_v2._process_discussion(normalized_query)
                elif classification.intent.value == "info":
                    result_v2 = self._pipeline_v2._process_knowledge(normalized_query)
                else:
                    result_v2 = self._pipeline_v2._process_action(
                        normalized_query, precomputed_analysis=precheck_analysis
                    )
            else:
                result_v2 = self._pipeline_v2._process_action(
                    normalized_query, precomputed_analysis=precheck_analysis
                )
            metrics['v2_pipeline_latency_ms'] = (time.time() - t0) * 1000
            metrics['rag_source'] = "rule"
            # Feedback loop pour les regles aussi
            feedback_recorded = False
            if self._feedback_loop:
                try:
                    t0 = time.time()
                    self._feedback_loop.record_interaction(
                        query=normalized_query,
                        tool_name=precheck_analysis.tool if precheck_analysis else "",
                        rag_score=1.0,
                        success=True
                    )
                    feedback_recorded = True
                    metrics['feedback_latency_ms'] = (time.time() - t0) * 1000
                except Exception:
                    pass
            metrics['total_latency_ms'] = (time.time() - start_time) * 1000
            enhanced = self._wrap_v2_result(result_v2, normalized_query, metrics)
            enhanced.feedback_recorded = feedback_recorded
            return enhanced

        # === ÉTAPE 3 : RAG (3-Tier ou V2) ===
        rag_source = "v2_fallback"
        rag_score = 0.0
        rag_results = []
        
        if self._rag_3tier:
            # Utiliser RAG 3-Tier (avec callback verbose M1)
            t0 = time.time()
            rag_results = self._rag_3tier.cascade_search(
                expanded_query,
                strategy="early_stop",
                top_k=5,
                on_step=rag_step_callback
            )
            metrics['rag_latency_ms'] = (time.time() - t0) * 1000

            if rag_results:
                rag_score = rag_results[0].get('score', 0.0)
                rag_source = rag_results[0].get('source', 'unknown')
        else:
            # Fallback RAG V2 : utiliser la FUSION RRF (semantic + keyword)
            # MAIS garder les scores semantic pour le ConfidenceCascader
            t0 = time.time()

            # Recherche semantic (pour les scores)
            try:
                _semantic = getattr(self._pipeline_v2._retriever, '_semantic', None) if self._pipeline_v2._retriever else None
                semantic_results = _semantic.search(expanded_query, top_k=10) if _semantic else []
            except Exception:
                semantic_results = []

            # Utiliser _retriever.retrieve qui fait semantic + keyword + RRF fusion (pour le ranking)
            v2_results = self._pipeline_v2._retriever.retrieve(expanded_query) if self._pipeline_v2._retriever else []
            metrics['rag_latency_ms'] = (time.time() - t0) * 1000

            if v2_results:
                # Créer un mapping ID -> score semantic
                semantic_scores = {r.id: r.score for r in semantic_results}

                # Détecter si on a court-circuité avec BM25
                # Court-circuit = rrf_score élevé (>0.10) indique BM25 dominant
                top1 = v2_results[0]
                is_bm25_shortcut = (
                    hasattr(top1, 'rrf_score') and top1.rrf_score > 0.10
                )

                # Convertir résultats en utilisant score semantic (pour cascade) mais ordre RRF (meilleur ranking)
                rag_results = []
                for i, r in enumerate(v2_results):
                    tool_id = r.id if hasattr(r, 'id') else r.metadata.get('name', '')

                    # Si court-circuit BM25 sur le top 1, utiliser score HIGH (0.90)
                    if i == 0 and is_bm25_shortcut:
                        cascade_score = 0.90  # BM25 très confiant
                    else:
                        # Sinon utiliser score semantic
                        cascade_score = semantic_scores.get(tool_id, 0.5)

                    rag_results.append({
                        'score': cascade_score,  # Score pour cascade
                        'rrf_score': r.rrf_score if hasattr(r, 'rrf_score') else 0.0,
                        'source': 'v2_bm25_shortcut' if (i == 0 and is_bm25_shortcut) else 'v2_fusion_rrf',
                        'metadata': r.metadata,
                        'document': r.document
                    })

                # Utiliser le score du top 1 (boost si court-circuit BM25)
                rag_score = rag_results[0]['score'] if rag_results else 0.0
                rag_source = rag_results[0]['source'] if rag_results else "v2_fusion_rrf"

                # === M1 callbacks simulés pour chemin V2 (Fix 3) ===
                # Émet les mêmes étapes que le RAG 3-tier pour que on_rag_step fire
                if rag_step_callback:
                    top_meta = v2_results[0].metadata if hasattr(v2_results[0], 'metadata') else {}
                    top_name = top_meta.get('name', '')
                    server = top_meta.get('server', '').upper()
                    if not server and '.' in top_name:
                        server = top_name.split('.')[0].upper()
                    elif not server:
                        server = 'UNKNOWN'
                    candidates = [
                        r.metadata.get('name', '') for r in v2_results[:3]
                        if hasattr(r, 'metadata')
                    ]
                    # Simuler registry_done (serveur identifié)
                    rag_step_callback("registry_done", {
                        "score": rag_score,
                        "server": server,
                        "candidates": candidates
                    })
                    # Simuler capabilities_done (outil identifié)
                    rag_step_callback("capabilities_done", {
                        "score": rag_score,
                        "tool": top_name,
                        "candidates": candidates
                    })
        
        # === ÉTAPE 4 : Confidence Cascader ===
        cascade_action = "execute"  # Default
        confidence_level = "high"   # Default
        should_inject_context = False

        if self._confidence_cascader and rag_results:
            t0 = time.time()
            cascade_result = self._confidence_cascader.cascade_detailed(
                rag_score=rag_score,
                rag_results=rag_results
            )
            metrics['cascade_latency_ms'] = (time.time() - t0) * 1000

            cascade_action = cascade_result['action'].value
            confidence_level = cascade_result.get('confidence_level', 'high')
            should_inject_context = cascade_result['should_inject_context']
        
        # === ÉTAPE 5 : Context Injector (si MEDIUM + gap faible) ===
        # Utiliser normalized_query au lieu de expanded_query pour éviter faux positifs
        # Les synonymes ont déjà servi pour le RAG, on n'en a plus besoin pour le routing
        query_for_pipeline = normalized_query
        context_injected = False
        enriched_query = None

        if should_inject_context and self._context_injector:
            t0 = time.time()
            # Déterminer N selon cascade_result
            n = 10 if cascade_action == "propose" else 5
            # Passer SessionMemory du pipeline V2
            session_memory = self._pipeline_v2._session
            query_for_pipeline = self._context_injector.inject(
                query=normalized_query,
                session_memory=session_memory,
                n=n
            )
            metrics['context_latency_ms'] = (time.time() - t0) * 1000

            # Vérifier si contexte réellement injecté (query changée)
            if query_for_pipeline != normalized_query:
                context_injected = True
                enriched_query = query_for_pipeline
        
        # === Callback "before_llm" : message LYRA avant EPHAISTOS (Fix 2) ===
        # Permet d'afficher un message de progression avant le long appel LLM
        if rag_step_callback and rag_results:
            top_tool = (rag_results[0].get('metadata') or {}).get('name', '?')
            rag_step_callback("before_llm", {
                "score": rag_score,
                "confidence_level": confidence_level,
                "tool": top_tool
            })

        # === ÉTAPE 6 : Pipeline V2 (EPHAISTOS, LYRA, HESTIA) ===
        # Passer les specs RAG déjà récupérées pour éviter un double retrieval
        t0 = time.time()

        # Toujours envoyer top 1 spec à EPHAISTOS
        # Même pour LOW confidence: EPHAISTOS se perd avec plusieurs candidats
        # Si le RAG trouve le bon outil en #1, mieux vaut lui donner juste celui-là
        num_specs = 1

        # Convertir rag_results en FusedResult pour _process_action
        from ..rag.fusion import FusedResult
        precomputed_specs = []
        for r in rag_results[:num_specs]:
            precomputed_specs.append(FusedResult(
                document=r['document'],
                metadata=r['metadata'],
                rrf_score=r.get('rrf_score', 0.0),
                id=r['metadata'].get('name', 'unknown'),
                semantic_rank=None,
                keyword_rank=None
            ))

        # Classifier l'intention
        if self._pipeline_v2._intent_classifier is not None:
            classification = self._pipeline_v2._intent_classifier.classify(query_for_pipeline)

            if classification.intent.value == "discussion":
                result_v2 = self._pipeline_v2._process_discussion(query_for_pipeline)
            elif classification.intent.value == "info":
                result_v2 = self._pipeline_v2._process_knowledge(query_for_pipeline)
            else:  # demande
                # Passer les specs pré-calculées à _process_action
                result_v2 = self._pipeline_v2._process_action(query_for_pipeline, precomputed_specs=precomputed_specs)
        else:
            # Fallback sans intent classifier
            result_v2 = self._pipeline_v2._process_action(query_for_pipeline, precomputed_specs=precomputed_specs)

        metrics['v2_pipeline_latency_ms'] = (time.time() - t0) * 1000
        
        # === ÉTAPE 7 : Feedback Loop ===
        feedback_recorded = False
        if self._feedback_loop:
            t0 = time.time()
            # Enregistrer meme en cas d'outil non trouve (miss = succes=False)
            success = result_v2.executed and result_v2.error is None
            tool_name = result_v2.tool_call.get('name', 'unknown') if result_v2.tool_call else 'unknown'

            self._feedback_loop.record_interaction(
                query=query,
                tool_name=tool_name,
                rag_score=rag_score,
                success=success
            )
            feedback_recorded = True
            metrics['feedback_latency_ms'] = (time.time() - t0) * 1000
        
        # === MÉTRIQUES FINALES ===
        metrics['total_latency_ms'] = (time.time() - start_time) * 1000

        # Si contexte injecté → confirmation requise (ambiguïté détectée)
        requires_confirmation = context_injected

        # Construire EnhancedPipelineResult
        return EnhancedPipelineResult(
            response=result_v2.response,
            query_type=result_v2.query_type,
            tool_call=result_v2.tool_call,
            pending_args=result_v2.pending_args,
            executed=result_v2.executed,
            error=result_v2.error,
            warnings=result_v2.warnings,
            execution_result=result_v2.execution_result,
            # Enhanced fields
            normalized_query=normalized_query,
            expanded_query=expanded_query,
            enriched_query=enriched_query,
            rag_source=rag_source,
            cascade_action=cascade_action,
            confidence_level=confidence_level,
            rag_score=rag_score,
            should_inject_context=should_inject_context,
            context_injected=context_injected,
            requires_confirmation=requires_confirmation,
            feedback_recorded=feedback_recorded,
            metrics=metrics
        )
    
    def _wrap_v2_result(
        self,
        result_v2: PipelineResult,
        query: str,
        metrics: dict
    ) -> EnhancedPipelineResult:
        """Enveloppe un résultat V2 dans EnhancedPipelineResult."""
        return EnhancedPipelineResult(
            response=result_v2.response,
            query_type=result_v2.query_type,
            tool_call=result_v2.tool_call,
            pending_args=result_v2.pending_args,
            executed=result_v2.executed,
            error=result_v2.error,
            warnings=result_v2.warnings,
            execution_result=result_v2.execution_result,
            # Enhanced fields (disabled)
            normalized_query=query,  # Inchangé
            expanded_query=query,
            rag_source="v2_fallback",
            cascade_action="execute",
            rag_score=0.0,
            should_inject_context=False,
            feedback_recorded=False,
            metrics=metrics
        )
    
    def reload_config(self, new_config: RAGEnhancedConfig):
        """Recharge la configuration enhanced.
        
        Args:
            new_config: Nouvelle configuration
        """
        self.enhanced_config = new_config
        
        # Réinitialiser composants si nécessaire
        # Note: Pour un hot reload complet, il faudrait réinitialiser
        # tous les composants avec la nouvelle config
        # Pour simplifier, on met juste à jour la référence
        # Les composants utiliseront la nouvelle config au prochain appel
        
        # Slang Normalizer
        if new_config.slang_normalizer.enabled != (self._slang_normalizer is not None):
            if new_config.slang_normalizer.enabled:
                self._slang_normalizer = get_default_normalizer()
            else:
                self._slang_normalizer = None
        
        # Synonym Expander
        if new_config.synonym_expander.enabled != (self._synonym_expander is not None):
            if new_config.synonym_expander.enabled:
                self._synonym_expander = get_synonym_expander()
            else:
                self._synonym_expander = None
        
        # Context Injector
        if new_config.context_injector.enabled != (self._context_injector is not None):
            if new_config.context_injector.enabled:
                self._context_injector = get_context_injector()
            else:
                self._context_injector = None
        
        # RAG 3-Tier
        if new_config.rag_3tier.enabled != (self._rag_3tier is not None):
            if new_config.rag_3tier.enabled:
                self._rag_3tier = get_rag_3tier()
                self._rag_3tier.initialize()
            else:
                self._rag_3tier = None
        
        # Confidence Cascader + Feedback Loop (liés)
        if new_config.feedback_loop.enabled != (self._feedback_loop is not None):
            if new_config.feedback_loop.enabled:
                self._confidence_cascader = get_confidence_cascader()
                self._feedback_loop = get_feedback_loop()
            else:
                self._confidence_cascader = None
                self._feedback_loop = None
