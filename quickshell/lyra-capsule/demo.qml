import QtQuick
import QtQuick.Layouts
import Quickshell
import "components"

// Demo sans demon : fait jouer a la capsule des messages factices (memes evenements
// que ceux du pont) dans une fenetre normale. Lancer via ./demo.
FloatingWindow {
    id: win
    implicitWidth: 520
    implicitHeight: 700
    color: "#070B17"
    title: "Lyra capsule (demo)"

    property int scenario: parseInt(Quickshell.env("DEMO_SCENARIO")) || 0
    property int step: -1
    property string mascot: Quickshell.env("DEMO_MASCOT") || "random"

    readonly property var scenarios: [
        { name: "Volume", steps: [
            { ms: 1100, m: { state: "idle" } },
            { ms: 2200, m: { state: "listening", you: "quel est le volume de la télé", level: 0.6 } },
            { ms: 1500, m: { state: "thinking", title: "Je regarde la télé" } },
            { ms: 6000, voice: "o", m: { state: "confirm", askId: "a1", say: "Je règle le volume de la télé. Tu confirmes ?",
                title: "Je règle le volume", confirm: { modify: true }, hints: ["oui", "non", "modifier"],
                display: { kind: "tv", title: "Télévision", items: [{ id: "volume", label: "Volume", value: 28, selected: true }, { id: "mute", label: "Muet", state: "non" }],
                           controls: [{ type: "slider", id: "volume", min: 0, max: 60, value: 28 }], pin: false } } },
            { ms: 2500, m: { state: "speaking", say: "C'est réglé, volume 28.", title: "Voilà" } },
            { ms: 2200, m: { state: "done", title: "C'est fait" } }
        ] },
        { name: "Choix", steps: [
            { ms: 1000, m: { state: "idle" } },
            { ms: 2200, m: { state: "listening", you: "arrête la machine virtuelle test", level: 0.5 } },
            { ms: 1500, m: { state: "thinking", title: "Je cherche la machine" } },
            { ms: 7000, voice: "test-vm", m: { state: "asking", askId: "a2", say: "Plusieurs machines correspondent. test-vm, ou testuuuuu ?",
                title: "Plusieurs machines correspondent", hints: ["test-vm", "la première", "testuuuuu"],
                display: { kind: "vms", title: "Machines virtuelles", items: [{ id: "test-vm", label: "test-vm", state: "running" }, { id: "testuuuuu", label: "testuuuuu", state: "shut off" }, { id: "dev-box", label: "dev-box", state: "paused" }], pin: false } } },
            { ms: 5000, voice: "o", m: { state: "warn", askId: "a3", say: "Attention, action sensible : arrêter test-vm. Dis oui pour confirmer.",
                title: "Action sensible", confirm: { modify: true }, hints: ["oui"] } },
            { ms: 2200, m: { state: "speaking", say: "test-vm est arrêtée.", title: "Voilà" } },
            { ms: 2200, m: { state: "done", title: "C'est fait" } }
        ] },
        { name: "Erreur", steps: [
            { ms: 1000, m: { state: "idle" } },
            { ms: 2000, m: { state: "listening", you: "allume les lumières", level: 0.55 } },
            { ms: 1500, m: { state: "thinking", title: "J'allume les lumières" } },
            { ms: 9000, m: { state: "error", title: "Ça n'a pas marché", say: "Il manque le groupe de lumières. Choisis-le dans la bulle.",
                display: { kind: "lights", title: "Groupes de lumières", items: [{ id: "salon", label: "Salon", state: "off" }, { id: "chambre", label: "Chambre", state: "on" }], pin: false } } }
        ] },
        { name: "Sessions", steps: [
            { ms: 1000, m: { state: "idle" } },
            { ms: 2200, m: { state: "listening", you: "montre-moi mes sessions", level: 0.5 } },
            { ms: 7000, voice: "2", m: { state: "asking", askId: "a4", say: "Voici tes sessions. Laquelle veux-tu ouvrir ?", title: "Laquelle veux-tu ouvrir ?",
                hints: ["installer", "lyra", "la deuxième"],
                display: { kind: "sessions", title: "Sessions Claude Code", items: [{ id: "1", label: "installer", state: "attend une réponse" }, { id: "2", label: "lyra", state: "travaille" }, { id: "3", label: "subtitle-ai", state: "terminée" }], pin: false } } },
            { ms: 2200, m: { state: "speaking", say: "J'ouvre la session lyra.", title: "Voilà" } },
            { ms: 2200, m: { state: "done", title: "C'est fait" } }
        ] }
    ]

    function play(index) { scenario = index; step = -1; capsule.handle({ event: "reset" }); capsule.resolved = ""; next() }
    function next() {
        var steps = scenarios[scenario].steps
        step = step + 1
        if (step >= steps.length) { scenario = (scenario + 1) % scenarios.length; step = 0; steps = scenarios[scenario].steps }
        var s = steps[step]
        capsule.handle(Object.assign({ event: "state" }, s.m))
        clock.remaining = s.ms
    }

    Timer {   // l'avance automatique se met en pause quand on survole la capsule
        id: clock
        property int remaining: 0
        interval: 50; repeat: true; running: win.step >= 0 || true
        onTriggered: {
            if (capsule.held || win.step < 0) return
            remaining -= interval
            var s = win.scenarios[win.scenario].steps[win.step]
            if (remaining <= 0) {
                if (s.voice && capsule.resolved === "") capsule.handle({ event: "voice_answer", value: s.voice })
                win.next()
            }
        }
    }
    Component.onCompleted: play(scenario)

    // Auto-test (DEMO_SELFTEST=1) : le premier a repondre gagne, le second est ignore.
    Timer {
        interval: 6500; running: Quickshell.env("DEMO_SELFTEST") === "1"
        onTriggered: {
            var seen = []
            capsule.answered.connect(function(id, v) { seen.push(id + "=" + v) })
            capsule.answer("confirm", "o")      // clic
            capsule.answer("confirm", "n")      // second clic : ignore
            capsule.resolveExternally("n")      // voix en retard : ignoree
            console.warn("SELFTEST emitted=" + JSON.stringify(seen) + " resolved=" + capsule.resolved)
            Qt.quit()
        }
    }

    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0; color: "#16224A" }
            GradientStop { position: 0.5; color: "#0B1226" }
            GradientStop { position: 1; color: "#070B17" }
        }
    }

    LyraCapsule {
        id: capsule
        x: (parent.width - width) / 2
        y: 24
        width: 440
        opacity: 1     // demo : toujours visible, meme au repos
        mascotSetting: win.mascot
        mascotsDir: Quickshell.env("LYRA_MASCOTS_DIR")
        asciiFile: Quickshell.shellPath("mascots.json")
        onAnswered: (id, value) => {
            console.warn("answered:", id, JSON.stringify(value))
            log.text = "answered(" + id + ", " + JSON.stringify(value) + ")"
            if (id !== "volume") clock.remaining = Math.min(clock.remaining, 900)
        }
    }

    ColumnLayout {
        anchors.bottom: parent.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.margins: 16
        spacing: 8
        Text { id: log; text: "survole la capsule pour figer ; clique pour repondre"; color: "#98A4C2"; font.family: CapsuleTheme.mono; font.pixelSize: 11 }
        Flow {
            Layout.fillWidth: true
            spacing: 6
            Repeater {
                model: win.scenarios
                Rectangle {
                    required property var modelData
                    required property int index
                    width: t1.implicitWidth + 20; height: 26; radius: 13
                    color: win.scenario === index ? "#7C6CF0" : "#1b2342"
                    Text { id: t1; anchors.centerIn: parent; text: parent.modelData.name; color: "#DCE2F2"; font.pixelSize: 12 }
                    TapHandler { onTapped: win.play(parent.index) }
                }
            }
            Repeater {
                model: ["random", "ascii", "owl", "cat", "robot", "rocket", "whale", "ghost"]
                Rectangle {
                    required property string modelData
                    width: t2.implicitWidth + 20; height: 26; radius: 13
                    color: win.mascot === modelData ? "#5EE1D0" : "#1b2342"
                    Text { id: t2; anchors.centerIn: parent; text: parent.modelData; color: win.mascot === parent.modelData ? "#05080F" : "#DCE2F2"; font.pixelSize: 12 }
                    TapHandler { onTapped: win.mascot = parent.modelData }
                }
            }
        }
    }
}
