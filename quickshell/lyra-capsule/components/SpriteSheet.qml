import QtQuick
import QtQuick.Effects

// Lecteur de feuille de sprites : <dir>/<mascotte>/<etat>.png, `cols` colonnes de
// cellules `cell` px (voir scripts/render_mascots.py). La feuille entiere est mise
// a l'echelle puis decalee dans un Item clippe ; une NumberAnimation cadence les
// frames (loopMs pour `frames` images), sans Timer ni rechargement de texture.
Item {
    id: root

    property url source
    property int frames: 60
    property int loopMs: 4000
    property int cols: 8
    property int rows: 8
    property int cell: 128
    property bool running: true
    // Teinte (0..1) appliquee par-dessus : erreur = mascotte qui rougit.
    property color tintColor: "#F0645A"
    property real tintAmount: 0

    readonly property int frame: Math.min(frames - 1, Math.floor(position))
    property real position: 0

    NumberAnimation on position {
        from: 0
        to: root.frames
        duration: Math.max(1, root.loopMs)
        loops: Animation.Infinite
        running: root.running && root.visible && root.frames > 1
    }

    Item {
        id: viewport
        anchors.fill: parent
        clip: true
        layer.enabled: root.tintAmount > 0
        layer.effect: MultiEffect {
            colorization: root.tintAmount
            colorizationColor: root.tintColor
        }

        Image {
            id: sheet
            source: root.source
            asynchronous: true
            smooth: true
            mipmap: true
            // Echelle : une cellule = tout le viewport.
            width: viewport.width * root.cols
            height: viewport.height * root.rows
            x: -(root.frame % root.cols) * viewport.width
            y: -Math.floor(root.frame / root.cols) * viewport.height
            fillMode: Image.Stretch
        }
    }
}
