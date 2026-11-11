import QtQuick
import Quickshell.Io

// Charge manifest.json (feuilles PNG) et mascots.json (creatures ASCII) et sert
// de table de consultation. Aucun chemin en dur : `dir` vient de l'environnement
// ou des reglages (bridge), `asciiFile` de l'installation de Lyra.
Item {
    id: root
    visible: false

    property string dir: ""          // dossier des feuilles (contient manifest.json)
    property string asciiFile: ""    // installer/assets/mascots.json

    property var manifest: ({})      // { size, fps, cols, mascots: { nom: { etat: {frames, loop_ms, rows} } } }
    property var ascii: ({})         // { nom: { n, c, ms, states } }
    readonly property var spriteNames: Object.keys(manifest.mascots || {}).sort()
    readonly property var asciiNames: Object.keys(ascii).sort()
    readonly property bool ready: spriteNames.length > 0 || asciiNames.length > 0

    function hasSprite(name) { return !!(manifest.mascots && manifest.mascots[name]) }
    function hasAscii(name) { return !!ascii[name] }

    // Reglage `capsule.mascot` : "random", "ascii", "ascii:<nom>" ou "<nom>".
    // Retourne { kind: "sprite"|"ascii"|"none", name }.
    function resolve(setting) {
        var s = String(setting || "random").trim()
        var pick = function(list) { return list[Math.floor(Math.random() * list.length)] }
        if (s === "ascii" || s.indexOf("ascii:") === 0) {
            var wanted = s.indexOf(":") > 0 ? s.slice(6) : ""
            if (hasAscii(wanted)) return { kind: "ascii", name: wanted }
            if (asciiNames.length) return { kind: "ascii", name: pick(asciiNames) }
        } else if (s === "random") {
            if (spriteNames.length) return { kind: "sprite", name: pick(spriteNames) }
        } else if (hasSprite(s)) {
            return { kind: "sprite", name: s }
        } else if (hasAscii(s)) {
            return { kind: "ascii", name: s }
        }
        // Repli : n'importe quelle source disponible plutot que rien.
        if (spriteNames.length) return { kind: "sprite", name: spriteNames[0] }
        if (asciiNames.length) return { kind: "ascii", name: asciiNames[0] }
        return { kind: "none", name: "" }
    }

    // Infos d'une feuille ; un etat absent retombe sur idle.
    function sheet(name, state) {
        var m = (manifest.mascots || {})[name] || {}
        var info = m[state] || m.idle
        if (!info) return null
        var cols = manifest.cols || 8
        return {
            url: "file://" + dir + "/" + name + "/" + (m[state] ? state : "idle") + ".png",
            frames: info.frames, loopMs: info.loop_ms,
            rows: info.rows || Math.ceil(info.frames / cols),
            cols: cols, cell: manifest.size || 128
        }
    }

    FileView {
        path: root.dir ? root.dir + "/manifest.json" : ""
        onLoaded: {
            try { root.manifest = JSON.parse(text()) }
            catch (e) { console.warn("capsule: manifest.json illisible:", e) }
        }
        onLoadFailed: console.warn("capsule: manifest.json introuvable dans", root.dir)
    }

    FileView {
        path: root.asciiFile
        onLoaded: {
            try {
                var data = JSON.parse(text()), flat = {}
                for (var group in data)
                    data[group].forEach(function(m) { flat[m.n] = m })
                root.ascii = flat
            } catch (e) { console.warn("capsule: mascots.json illisible:", e) }
        }
        onLoadFailed: console.warn("capsule: mascots.json introuvable:", root.asciiFile)
    }
}
