pragma Singleton
import QtQuick
QtObject {
    readonly property bool dark: appearance.dark
    readonly property bool highContrast: appearance.highContrast
    readonly property bool motion: !appearance.reduceMotion
    readonly property color foreground: highContrast ? (dark ? "#ffffff" : "#000000") : (dark ? "#f2f4f8" : "#202632")
    readonly property color secondary: highContrast ? foreground : (dark ? "#b1bac9" : "#626d7c")
    readonly property color muted: highContrast ? foreground : (dark ? "#8f9bad" : "#768394")
    readonly property color surface: dark ? "#242933" : "#ffffff"
    readonly property color canvas: dark ? "#191d25" : "#f4f6fa"
    readonly property color field: dark ? "#191e27" : "#f2f4f8"
    readonly property color line: highContrast ? foreground : (dark ? "#3c4453" : "#dfe5ed")
    readonly property color accent: dark ? "#6eacff" : "#1767db"
    readonly property color accentSoft: dark ? "#243c5b" : "#e5efff"
    readonly property color error: dark ? "#ffaaaa" : "#b93537"
    readonly property color success: dark ? "#73d9b4" : "#20785c"
    readonly property string font: Qt.platform.os === "windows" ? "Microsoft YaHei UI" : "Sans Serif"
    readonly property int fast: motion ? 150 : 0
    readonly property int duration: motion ? 240 : 0
    function read(path) {
        let value = preferences.draft;
        const parts = path.split(".");
        for (let i = 0; i < parts.length; ++i) value = value[parts[i]];
        return value;
    }
    function errorFor(path) { return preferences.errors[path] || ""; }
}
