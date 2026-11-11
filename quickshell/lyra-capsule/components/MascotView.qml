import QtQuick

// Mascotte de la capsule : feuille de sprites ou creature ASCII, choisie par le
// reglage capsule.mascot. L'etat vocal (idle, listening...) est traduit en etat de
// feuille ; l'erreur utilise la feuille err et rougit en plus (teinte).
Item {
    id: root

    required property MascotCatalog catalog
    property string setting: "random"
    property string state: "idle"        // etat vocal
    property string phase: ""            // "speaking" pendant une question parlee
    property real size: 64
    readonly property string spriteState: CapsuleTheme.spriteState(state, phase)

    property var choice: ({ kind: "none", name: "" })
    readonly property string name: choice.name

    implicitWidth: size
    implicitHeight: size

    // Nouveau tirage (a appeler au debut d'une session : le mode aleatoire change
    // de mascotte a chaque fois, jamais au milieu).
    function reroll() { choice = catalog.resolve(setting) }

    onSettingChanged: reroll()
    Connections { target: root.catalog; function onReadyChanged() { root.reroll() } }
    Component.onCompleted: reroll()

    // --- sprites ---
    SpriteSheet {
        id: sprite
        anchors.fill: parent
        visible: root.choice.kind === "sprite"
        readonly property var info: root.choice.kind === "sprite"
            ? root.catalog.sheet(root.choice.name, root.spriteState) : null
        source: info ? info.url : ""
        frames: info ? info.frames : 1
        loopMs: info ? info.loopMs : 1000
        rows: info ? info.rows : 1
        cols: info ? info.cols : 8
        cell: info ? info.cell : 128
        tintAmount: root.state === "error" ? 0.28 : 0
        // petit "pop" quand l'etat change
        onSourceChanged: pop.restart()
        SequentialAnimation {
            id: pop
            NumberAnimation { target: sprite; property: "scale"; to: 0.88; duration: 70 }
            NumberAnimation { target: sprite; property: "scale"; to: 1; duration: 260; easing.type: Easing.OutBack }
        }
    }

    // --- ASCII : frames de 5 lignes de 9 colonnes ---
    Text {
        id: art
        anchors.centerIn: parent
        visible: root.choice.kind === "ascii"
        property var entry: root.choice.kind === "ascii" ? root.catalog.ascii[root.choice.name] : null
        property string asciiState: root.state === "error" ? "err" : root.spriteState
        property int index: 0
        readonly property var colors: ({ o: "#f6c177", g: "#82d69c", p: "#eb6f92", b: "#7fb2e0", m: "#c4a7e7" })
        readonly property var frames: entry ? (entry.states[asciiState] || entry.states.idle || []) : []
        text: frames.length ? frames[index % frames.length].join("\n") : ""
        color: root.state === "error" ? CapsuleTheme.err : (entry ? (colors[entry.c] || CapsuleTheme.inkSoft) : CapsuleTheme.inkSoft)
        font.family: CapsuleTheme.mono
        font.pixelSize: Math.max(7, Math.floor(root.size / 5.6))
        lineHeight: 0.95
        onAsciiStateChanged: index = 0
        Timer {
            interval: art.entry ? art.entry.ms : 120
            repeat: true
            running: art.visible && art.frames.length > 1
            onTriggered: art.index++
        }
    }
}
