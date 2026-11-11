import QtQuick
import QtQuick.Layouts

// Rend un payload "display" du demon (lyra/daemon/display.py) :
//   { kind, title, items: [{id, label, value?, state?, selected?}],
//     controls?: [{type: "slider", id, min, max, value}], pin }
// Tout est du texte d'affichage : on ne l'interprete jamais. Un clic emet
// itemClicked(id) avec l'id propose (jamais un texte libre).
ColumnLayout {
    id: root

    property var display: null
    property bool interactive: true
    property string picked: ""          // id deja repondu (voix ou clic) : verrouille la liste
    readonly property bool locked: picked !== ""
    readonly property var items: (display && display.items) ? display.items : []
    readonly property var controls: (display && display.controls) ? display.controls : []
    // un item qui porte le meme id qu'un curseur est affiche par le curseur lui-meme
    readonly property var rows: items.filter(function(i) {
        return !controls.some(function(c) { return c.id === i.id })
    })
    readonly property bool numbered: display && (display.kind === "choices" || display.kind === "sessions")

    signal itemClicked(string id)
    signal sliderCommitted(string id, int value)

    spacing: 8

    Repeater {
        model: root.rows

        delegate: Rectangle {
            id: row
            required property var modelData
            required property int index
            readonly property bool chosen: root.picked === modelData.id
            readonly property bool active: chosen || (!root.locked && modelData.selected === true)
            readonly property bool clickable: root.interactive && !root.locked

            Layout.fillWidth: true
            Layout.preferredHeight: 40
            radius: 12
            color: active ? Qt.rgba(0.49, 0.42, 0.94, 0.18)
                          : (hover.hovered && clickable ? Qt.rgba(1, 1, 1, 0.07) : CapsuleTheme.fill)
            border.width: 1
            border.color: active ? Qt.rgba(0.65, 0.61, 1, 0.6) : Qt.rgba(1, 1, 1, 0.06)
            opacity: root.locked && !chosen ? 0.45 : 1
            Behavior on color { ColorAnimation { duration: 140 } }
            Behavior on opacity { NumberAnimation { duration: 240 } }

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 10
                anchors.rightMargin: 10
                spacing: 10

                Rectangle {
                    visible: root.numbered
                    Layout.preferredWidth: 22
                    Layout.preferredHeight: 22
                    radius: 11
                    color: Qt.rgba(1, 1, 1, 0.08)
                    Text {
                        anchors.centerIn: parent
                        text: row.index + 1
                        color: CapsuleTheme.inkSoft
                        font.family: CapsuleTheme.font
                        font.pixelSize: 11
                        font.weight: Font.Bold
                    }
                }
                Text {
                    Layout.fillWidth: true
                    text: row.modelData.label || row.modelData.id
                    elide: Text.ElideRight
                    color: CapsuleTheme.ink
                    font.family: CapsuleTheme.font
                    font.pixelSize: 14
                    font.weight: row.active ? Font.DemiBold : Font.Medium
                }
                Text {
                    visible: row.modelData.value !== undefined && !root.controls.length
                    text: String(row.modelData.value)
                    color: CapsuleTheme.inkSoft
                    font.family: CapsuleTheme.mono
                    font.pixelSize: 12
                }
                Rectangle {
                    visible: !!row.modelData.state
                    readonly property color tone: CapsuleTheme.badgeTone(row.modelData.state)
                    Layout.preferredWidth: badge.implicitWidth + 18
                    Layout.preferredHeight: 20
                    radius: 10
                    color: Qt.rgba(tone.r, tone.g, tone.b, 0.15)
                    Text {
                        id: badge
                        anchors.centerIn: parent
                        text: row.modelData.state || ""
                        color: parent.tone
                        font.family: CapsuleTheme.font
                        font.pixelSize: 11
                        font.weight: Font.DemiBold
                    }
                }
            }

            HoverHandler { id: hover; cursorShape: row.clickable ? Qt.PointingHandCursor : Qt.ArrowCursor }
            TapHandler {
                enabled: row.clickable
                onTapped: root.itemClicked(row.modelData.id)
            }
        }
    }

    // Controles : curseur (volume...). Valeur locale pendant le glisser, emise au relachement.
    Repeater {
        model: root.controls.filter(function(c) { return c.type === "slider" })

        delegate: Rectangle {
            id: gauge
            required property var modelData
            readonly property real lo: modelData.min
            readonly property real hi: Math.max(modelData.max, modelData.min + 1)
            property real current: modelData.value
            readonly property real ratio: Math.max(0, Math.min(1, (current - lo) / (hi - lo)))

            Layout.fillWidth: true
            Layout.preferredHeight: 62
            radius: 14
            color: CapsuleTheme.fill
            border.width: 1
            border.color: Qt.rgba(1, 1, 1, 0.06)
            opacity: root.locked ? 0.5 : 1

            Text {
                x: 14; y: 9
                text: "Volume"
                color: CapsuleTheme.inkSoft
                font.family: CapsuleTheme.font
                font.pixelSize: 11
                font.letterSpacing: 1.2
                font.capitalization: Font.AllUppercase
            }
            Text {
                anchors.right: parent.right
                anchors.rightMargin: 14
                y: 6
                text: Math.round(gauge.current)
                color: CapsuleTheme.ink
                font.family: CapsuleTheme.mono
                font.pixelSize: 16
                font.weight: Font.Medium
            }
            Rectangle {
                id: track
                x: 14; y: 38
                width: parent.width - 28
                height: 8
                radius: 4
                color: Qt.rgba(1, 1, 1, 0.08)
                Rectangle {
                    width: track.width * gauge.ratio
                    height: parent.height
                    radius: 4
                    gradient: Gradient {
                        orientation: Gradient.Horizontal
                        GradientStop { position: 0; color: CapsuleTheme.accent }
                        GradientStop { position: 1; color: CapsuleTheme.accentHi }
                    }
                }
                Rectangle {
                    x: track.width * gauge.ratio - width / 2
                    y: -5
                    width: 18; height: 18; radius: 9
                    color: "#ffffff"
                    border.width: 3
                    border.color: CapsuleTheme.accent
                }
            }
            MouseArea {
                enabled: root.interactive && !root.locked
                x: 6; y: 28
                width: parent.width - 12
                height: 28
                cursorShape: Qt.PointingHandCursor
                function setFrom(mx) {
                    var r = Math.max(0, Math.min(1, (mx - 8) / (width - 16)))
                    gauge.current = Math.round(gauge.lo + r * (gauge.hi - gauge.lo))
                }
                onPressed: mouse => setFrom(mouse.x)
                onPositionChanged: mouse => { if (pressed) setFrom(mouse.x) }
                onReleased: root.sliderCommitted(gauge.modelData.id, Math.round(gauge.current))
            }
        }
    }
}
