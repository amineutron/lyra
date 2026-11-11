pragma Singleton
import QtQuick

// Jetons visuels de la capsule vocale (reference : maquette HTML validee).
// Volontairement nomme CapsuleTheme : "Palette" est masque par QtQuick (Qt 6.10+).
QtObject {
    readonly property color paper: "#05080F"
    readonly property color bubbleBg: "#0B1022"
    readonly property color ink: "#DCE2F2"
    readonly property color inkSoft: "#98A4C2"
    readonly property color inkDim: "#6E7A99"
    readonly property color line: Qt.rgba(1, 1, 1, 0.09)
    readonly property color fill: Qt.rgba(1, 1, 1, 0.045)
    readonly property color accent: "#7C6CF0"
    readonly property color accentHi: "#A79BFF"
    readonly property color voice: "#5EE1D0"
    readonly property color warn: "#F2B84B"
    readonly property color err: "#F0645A"
    readonly property color ok: "#5FD39A"

    readonly property string font: "Space Grotesk"
    readonly property string mono: "JetBrains Mono"

    readonly property int easeOut: Easing.OutCubic
    readonly property int dur: 560

    // Couleur ("tone") de chaque etat vocal.
    function tone(state) {
        switch (state) {
        case "listening": case "asking": case "confirm": return voice
        case "thinking": case "speaking": return accentHi
        case "warn": return warn
        case "done": return ok
        case "error": return err
        default: return inkSoft
        }
    }
    function kicker(state) {
        switch (state) {
        case "listening": return "Écoute"
        case "thinking": return "Réflexion"
        case "speaking": return "Parole"
        case "asking": return "Question"
        case "confirm": return "Confirmation"
        case "warn": return "Attention"
        case "done": return "Terminé"
        case "error": return "Erreur"
        default: return "Repos"
        }
    }
    function defaultTitle(state) {
        switch (state) {
        case "listening": return "Je t'écoute"
        case "thinking": return "Je réfléchis"
        case "speaking": return "Voilà"
        case "asking": return "J'ai une question"
        case "confirm": return "Tu confirmes ?"
        case "warn": return "Action sensible"
        case "done": return "C'est fait"
        case "error": return "Ça n'a pas marché"
        default: return "Lyra est au repos"
        }
    }
    // Etat vocal -> etat de feuille de sprites (sleep, idle, work, busy, ok, err).
    function spriteState(state, phase) {
        switch (state) {
        case "idle": return "sleep"
        case "listening": return "idle"
        case "thinking": return "work"
        case "speaking": return "busy"
        case "done": return "ok"
        case "error": return "err"
        default: return phase === "speaking" ? "busy" : "idle"
        }
    }
    // Couleur d'un badge d'etat (vm, lumiere, session).
    function badgeTone(s) {
        var v = String(s || "").toLowerCase()
        if (["running", "on", "ok", "done", "terminee", "active"].indexOf(v) >= 0) return ok
        if (["off", "shut off", "stopped", "arretee", "closed"].indexOf(v) >= 0) return inkDim
        if (["error", "crashed", "failed"].indexOf(v) >= 0) return err
        return warn
    }
}
