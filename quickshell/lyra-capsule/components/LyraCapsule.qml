import QtQuick
import QtQuick.Layouts

// Capsule vocale de Lyra : une pilule (mascotte + etat + texte) qui s'ouvre pendant
// une session, et une bulle interactive en dessous quand le demon envoie un payload
// "display". Voix et clic marchent en parallele : la premiere reponse gagne, la
// capsule emet `answered(id, value)` une seule fois par question.
//
// Entree : handle({event: ...}) (voir bridge/lyra_capsule_bridge.py) ; sortie : signaux.
Item {
    id: root

    // --- configuration ---
    property string mascotSetting: "random"   // reglage capsule.mascot
    property string mascotsDir: ""
    property string asciiFile: ""
    property int doneHoldMs: 2400
    property int errorHoldMs: 6500

    // --- etat courant (ecrit par handle()) ---
    property string state: "idle"   // idle listening thinking speaking asking confirm warn done error
    property string title: ""
    property string you: ""
    property string say: ""
    property var hints: []
    property bool confirm: false    // boutons oui / non
    property bool canModify: false  // + bouton "modifier" (m)
    property string askId: ""
    property var display: null
    property real level: 0          // niveau micro / voix 0..1
    property bool pinned: false
    property string resolved: ""    // reponse deja donnee a la question en cours

    readonly property bool held: hoverHeld || pinned
    readonly property bool wanted: state !== "idle" || pinned
    readonly property bool waiting: state === "asking" || state === "confirm" || state === "warn"
    readonly property bool opened: state !== "idle"
    readonly property alias pill: pillBox
    readonly property alias bubble: bubbleBox
    readonly property alias mascot: mascotView

    signal answered(string id, var value)
    signal pinToggled(bool pinned)

    implicitWidth: 440
    implicitHeight: column.implicitHeight
    opacity: wanted ? 1 : 0
    Behavior on opacity { NumberAnimation { duration: 420 } }

    // ---------- API ----------
    function handle(msg) {
        switch (msg.event) {
        case "state": applyState(msg); break
        case "display": setDisplay(msg.display); break
        case "level": level = Math.max(0, Math.min(1, Number(msg.level) || 0)); break
        case "voice_answer": resolveExternally(String(msg.value)); break
        case "settings":
            if (msg.mascot !== undefined) mascotSetting = String(msg.mascot)
            break
        case "reset": state = "idle"; display = null; resolved = ""; break
        }
    }

    function applyState(msg) {
        var next = msg.state || "idle"
        if (state === "idle" && next !== "idle") mascotView.reroll()   // nouvelle session
        var newAsk = msg.askId !== undefined ? String(msg.askId) : ""
        if (newAsk !== askId || !(next === "asking" || next === "confirm" || next === "warn"))
            resolved = ""
        askId = newAsk
        state = next
        title = msg.title !== undefined ? msg.title : CapsuleTheme.defaultTitle(next)
        you = msg.you || ""
        say = msg.say || ""
        hints = msg.hints || []
        confirm = !!msg.confirm
        canModify = !!(msg.confirm && msg.confirm.modify)
        if (msg.level !== undefined) level = Number(msg.level) || 0
        if ("display" in msg) setDisplay(msg.display)
        if (next === "idle" && !pinned) display = null
    }

    function setDisplay(d) {
        display = d
        if (d && d.pin === true) pinned = true
    }

    // Reponse venue d'ailleurs (voix reconnue par le demon) : on verrouille sans reemettre.
    function resolveExternally(value) { if (resolved === "") resolved = value }

    function answer(id, value) {
        if (resolved !== "") return            // le premier gagne
        resolved = String(value)
        answered(id, value)
    }

    function togglePin() { pinned = !pinned; pinToggled(pinned) }

    // ---------- survol = maintien ----------
    property bool hoverHeld: false
    HoverHandler { id: pillHover; target: pillBox }
    HoverHandler { id: bubbleHover; target: bubbleBox }
    readonly property bool hoverNow: pillHover.hovered || bubbleHover.hovered
    onHoverNowChanged: {
        if (hoverNow) { releaseTimer.stop(); hoverHeld = true }
        else releaseTimer.restart()            // tolere la traversee du vide entre pilule et bulle
    }
    Timer { id: releaseTimer; interval: 450; onTriggered: root.hoverHeld = false }

    // Fermeture automatique apres done / error, jamais pendant une session,
    // jamais tant qu'on survole ou qu'on a epingle.
    Timer {
        interval: root.state === "error" ? root.errorHoldMs : root.doneHoldMs
        running: (root.state === "done" || root.state === "error") && !root.held
        onTriggered: { root.state = "idle"; if (!root.pinned) root.display = null }
    }

    // ---------- visuel ----------
    readonly property color tone: CapsuleTheme.tone(state)
    readonly property color edge: state === "idle" ? CapsuleTheme.line
        : Qt.rgba(tone.r, tone.g, tone.b, 0.55)

    ColumnLayout {
        id: column
        width: parent.width
        spacing: 12

        // ===== pilule =====
        Rectangle {
            id: pillBox
            Layout.alignment: Qt.AlignHCenter
            Layout.preferredWidth: root.opened ? 440 : 232
            Layout.preferredHeight: head.y + head.implicitHeight + body.height + (root.opened ? 6 : 7)
            radius: root.opened ? 28 : 22
            color: CapsuleTheme.paper
            border.width: 1
            border.color: root.edge
            clip: true
            Behavior on Layout.preferredWidth { NumberAnimation { duration: CapsuleTheme.dur; easing.type: CapsuleTheme.easeOut } }
            Behavior on radius { NumberAnimation { duration: CapsuleTheme.dur; easing.type: CapsuleTheme.easeOut } }
            Behavior on border.color { ColorAnimation { duration: 400 } }

            RowLayout {
                id: head
                x: root.opened ? 12 : 8
                y: root.opened ? 12 : 7
                width: parent.width - x - 16
                spacing: 12
                Behavior on x { NumberAnimation { duration: CapsuleTheme.dur; easing.type: CapsuleTheme.easeOut } }
                Behavior on y { NumberAnimation { duration: CapsuleTheme.dur; easing.type: CapsuleTheme.easeOut } }

                MascotView {
                    id: mascotView
                    catalog: mascotCatalog
                    setting: root.mascotSetting
                    state: root.state
                    phase: root.waiting && root.say !== "" ? "speaking" : ""
                    size: root.opened ? 64 : 30
                    Layout.preferredWidth: size
                    Layout.preferredHeight: size
                    Behavior on size { NumberAnimation { duration: CapsuleTheme.dur; easing.type: CapsuleTheme.easeOut } }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 1
                    Text {
                        visible: root.opened
                        text: CapsuleTheme.kicker(root.state)
                        color: root.tone
                        font.family: CapsuleTheme.font
                        font.pixelSize: 11
                        font.weight: Font.Bold
                        font.letterSpacing: 1.7
                        font.capitalization: Font.AllUppercase
                        Behavior on color { ColorAnimation { duration: 300 } }
                    }
                    Text {
                        Layout.fillWidth: true
                        text: root.opened ? root.title : CapsuleTheme.defaultTitle("idle")
                        color: CapsuleTheme.ink
                        font.family: CapsuleTheme.font
                        font.pixelSize: root.opened ? 16 : 14
                        font.weight: Font.Medium
                        wrapMode: root.opened ? Text.WordWrap : Text.NoWrap
                        elide: root.opened ? Text.ElideNone : Text.ElideRight
                        maximumLineCount: 2
                    }
                }
                Row {
                    id: meter
                    spacing: 3
                    Layout.alignment: Qt.AlignVCenter
                    property real lv: root.level
                    Timer {   // sans niveau reel, la parole de Lyra anime quand meme les barres
                        interval: 110; repeat: true
                        running: root.state === "speaking" && root.level < 0.01
                        onTriggered: meter.lv = 0.25 + Math.random() * 0.7
                        onRunningChanged: if (!running) meter.lv = root.level
                    }
                    Repeater {
                        model: [0.55, 0.9, 1, 0.75, 0.5]
                        Rectangle {
                            required property real modelData
                            width: 3
                            height: Math.max(3, 4 + meter.lv * modelData * 18)
                            anchors.verticalCenter: parent.verticalCenter
                            radius: 2
                            color: root.tone
                            opacity: root.state === "idle" || root.state === "done" ? 0.25 : 0.85
                            Behavior on height { NumberAnimation { duration: 90 } }
                        }
                    }
                }
            }

            // corps : ce que dit l'utilisateur, ce que dit Lyra, boutons de confirmation
            Item {
                id: body
                y: head.y + head.implicitHeight
                width: parent.width
                height: root.opened ? bodyCol.implicitHeight + 18 : 0
                clip: true
                Behavior on height { NumberAnimation { duration: CapsuleTheme.dur; easing.type: CapsuleTheme.easeOut } }

                ColumnLayout {
                    id: bodyCol
                    x: 20
                    width: parent.width - 40
                    spacing: 10

                    RowLayout {
                        visible: root.you !== ""
                        Layout.fillWidth: true
                        spacing: 10
                        Text { text: "TOI"; color: CapsuleTheme.inkDim; font.family: CapsuleTheme.font; font.pixelSize: 11; font.weight: Font.Bold; font.letterSpacing: 1.4; Layout.preferredWidth: 42 }
                        Text { Layout.fillWidth: true; text: root.you; wrapMode: Text.WordWrap; color: CapsuleTheme.voice; font.family: CapsuleTheme.font; font.pixelSize: 15 }
                    }
                    RowLayout {
                        visible: root.say !== ""
                        Layout.fillWidth: true
                        spacing: 10
                        Text { text: "LYRA"; color: CapsuleTheme.inkDim; font.family: CapsuleTheme.font; font.pixelSize: 11; font.weight: Font.Bold; font.letterSpacing: 1.4; Layout.preferredWidth: 42 }
                        Text { Layout.fillWidth: true; text: root.say; wrapMode: Text.WordWrap; color: CapsuleTheme.ink; font.family: CapsuleTheme.font; font.pixelSize: 15; lineHeight: 1.15 }
                    }

                    // confirmation O / n / m
                    Flow {
                        visible: root.confirm
                        Layout.fillWidth: true
                        spacing: 8
                        Repeater {
                            model: root.canModify
                                ? [{ k: "o", t: "oui" }, { k: "n", t: "non" }, { k: "m", t: "modifier" }]
                                : [{ k: "o", t: "oui" }, { k: "n", t: "non" }]
                            Rectangle {
                                id: chip
                                required property var modelData
                                readonly property bool picked: root.resolved === modelData.k
                                width: label.implicitWidth + 28
                                height: 30
                                radius: 15
                                color: picked ? Qt.rgba(root.tone.r, root.tone.g, root.tone.b, 0.22)
                                              : (chipHover.hovered && root.resolved === "" ? Qt.rgba(1, 1, 1, 0.1) : CapsuleTheme.fill)
                                border.width: 1
                                border.color: picked ? root.tone : CapsuleTheme.line
                                opacity: root.resolved !== "" && !picked ? 0.4 : 1
                                Behavior on color { ColorAnimation { duration: 140 } }
                                Text { id: label; anchors.centerIn: parent; text: chip.modelData.t; color: CapsuleTheme.ink; font.family: CapsuleTheme.font; font.pixelSize: 13; font.weight: Font.Medium }
                                HoverHandler { id: chipHover; cursorShape: Qt.PointingHandCursor }
                                TapHandler { onTapped: root.answer("confirm", chip.modelData.k) }
                            }
                        }
                    }

                    // indices vocaux ("dis : ...")
                    Flow {
                        visible: root.hints.length > 0 && root.resolved === ""
                        Layout.fillWidth: true
                        spacing: 6
                        Text { text: "Dis :"; color: CapsuleTheme.inkDim; font.family: CapsuleTheme.font; font.pixelSize: 12; height: 22; verticalAlignment: Text.AlignVCenter }
                        Repeater {
                            model: root.hints
                            Rectangle {
                                required property string modelData
                                width: hintText.implicitWidth + 16
                                height: 22
                                radius: 11
                                color: "transparent"
                                border.width: 1
                                border.color: CapsuleTheme.line
                                Text { id: hintText; anchors.centerIn: parent; text: parent.modelData; color: CapsuleTheme.inkSoft; font.family: CapsuleTheme.mono; font.pixelSize: 11 }
                            }
                        }
                    }
                }
            }
        }

        // ===== bulle interactive =====
        Rectangle {
            id: bubbleBox
            Layout.alignment: Qt.AlignHCenter
            Layout.preferredWidth: 360
            Layout.preferredHeight: bubbleCol.implicitHeight + 28
            visible: root.display !== null && opacity > 0.01
            opacity: root.display !== null ? 1 : 0
            Behavior on opacity { NumberAnimation { duration: 320 } }
            radius: 20
            color: CapsuleTheme.bubbleBg
            border.width: 1
            border.color: root.held ? Qt.rgba(0.65, 0.61, 1, 0.7) : Qt.rgba(0.49, 0.42, 0.94, 0.35)
            Behavior on border.color { ColorAnimation { duration: 300 } }

            // pointe vers la pilule
            Rectangle {
                width: 12; height: 12
                rotation: 45
                x: parent.width / 2 - 6
                y: -7
                color: CapsuleTheme.bubbleBg
                z: -1
                border.width: 1
                border.color: parent.border.color
            }

            ColumnLayout {
                id: bubbleCol
                x: 14; y: 14
                width: parent.width - 28
                spacing: 10

                RowLayout {
                    Layout.fillWidth: true
                    Text {
                        Layout.fillWidth: true
                        text: root.display ? root.display.title : ""
                        elide: Text.ElideRight
                        color: CapsuleTheme.inkSoft
                        font.family: CapsuleTheme.font
                        font.pixelSize: 11
                        font.letterSpacing: 1.2
                        font.capitalization: Font.AllUppercase
                    }
                    Rectangle {
                        Layout.preferredWidth: pinText.implicitWidth + 20
                        Layout.preferredHeight: 24
                        radius: 12
                        color: root.pinned ? Qt.rgba(0.49, 0.42, 0.94, 0.3) : "transparent"
                        border.width: 1
                        border.color: root.pinned ? CapsuleTheme.accentHi : CapsuleTheme.line
                        Text { id: pinText; anchors.centerIn: parent; text: root.pinned ? "Épinglée" : "Épingler"; color: root.pinned ? CapsuleTheme.ink : CapsuleTheme.inkSoft; font.family: CapsuleTheme.font; font.pixelSize: 11 }
                        HoverHandler { cursorShape: Qt.PointingHandCursor }
                        TapHandler { onTapped: root.togglePin() }
                    }
                }

                DisplayView {
                    Layout.fillWidth: true
                    display: root.display
                    picked: root.resolved
                    onItemClicked: id => root.answer(id, id)
                    onSliderCommitted: (id, value) => root.answered(id, value)
                }

                Text {
                    visible: root.waiting && root.resolved === ""
                    text: "Clique, ou dis ton choix à voix haute."
                    color: CapsuleTheme.inkDim
                    font.family: CapsuleTheme.font
                    font.pixelSize: 12
                }
            }
        }
    }

    MascotCatalog {
        id: mascotCatalog
        dir: root.mascotsDir
        asciiFile: root.asciiFile
    }
}
