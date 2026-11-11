//@ pragma UseQApplication
import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import "components"

// Capsule vocale de Lyra, instance Quickshell autonome :
//     quickshell -c lyra-capsule        (dossier installe dans ~/.config/quickshell/)
//     quickshell -p <depot>/quickshell/lyra-capsule
// Elle ne touche pas au shell.qml de la barre : c'est un second processus.
//
// Environnement (tous optionnels) :
//   LYRA_MASCOTS_DIR     feuilles PNG (defaut : $XDG_DATA_HOME/lyra/mascots)
//   LYRA_MASCOTS_ASCII   mascots.json ASCII (defaut : installe avec Lyra, voir README)
//   LYRA_CAPSULE_MASCOT  reglage capsule.mascot si config.yaml n'en donne pas
//   LYRA_CAPSULE_TOP     marge haute en px (defaut 52)
//   LYRA_PYTHON          interpreteur du pont (defaut python3)
ShellRoot {
    id: shellRoot
    readonly property string dataHome: Quickshell.env("XDG_DATA_HOME") || (Quickshell.env("HOME") + "/.local/share")

    PanelWindow {
        id: win
        visible: capsule.wanted || capsule.opacity > 0.01
        color: "transparent"
        anchors.top: true                       // centre horizontalement
        margins.top: parseInt(Quickshell.env("LYRA_CAPSULE_TOP")) || 52
        implicitWidth: 460
        implicitHeight: 640
        exclusionMode: ExclusionMode.Ignore     // ne pousse aucune fenetre
        WlrLayershell.layer: WlrLayer.Overlay
        WlrLayershell.namespace: "lyra-capsule"
        WlrLayershell.keyboardFocus: WlrKeyboardFocus.None

        // Clics : seulement sur la pilule et la bulle, le reste de la fenetre est traversant.
        mask: Region {
            item: capsule.pill
            Region { item: capsule.bubble }
        }

        LyraCapsule {
            id: capsule
            anchors.horizontalCenter: parent.horizontalCenter
            width: 440
            mascotsDir: Quickshell.env("LYRA_MASCOTS_DIR") || (shellRoot.dataHome + "/lyra/mascots")
            asciiFile: Quickshell.env("LYRA_MASCOTS_ASCII") || Quickshell.shellPath("mascots.json")
            mascotSetting: Quickshell.env("LYRA_CAPSULE_MASCOT") || "random"
            onAnswered: (id, value) => bridge.send({ type: "answer", id: id, value: value })
        }
    }

    // Pont vers le demon : JSON-lines sur stdin/stdout (voir bridge/lyra_capsule_bridge.py).
    Process {
        id: bridge
        command: [Quickshell.env("LYRA_PYTHON") || "python3", Quickshell.shellPath("bridge/lyra_capsule_bridge.py")]
        running: true
        stdinEnabled: true
        stdout: SplitParser {
            onRead: line => {
                try { capsule.handle(JSON.parse(line)) }
                catch (e) { console.warn("capsule: message du pont illisible:", e, line.slice(0, 120)) }
            }
        }
        stderr: SplitParser { onRead: line => console.log("[bridge]", line) }
        onExited: restart.start()

        function send(message) { write(JSON.stringify(message) + "\n") }
    }
    Timer { id: restart; interval: 3000; onTriggered: bridge.running = true }
}
