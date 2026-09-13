import QtQuick
Item {
    id: root
    property string name: "overview"
    property color color: Theme.secondary
    property size sourceSize: Qt.size(width, height)
    implicitWidth: 20
    implicitHeight: 20
    property var paths: ({
        overview: '<rect x="3" y="3" width="7" height="7" rx="2"/><rect x="14" y="3" width="7" height="7" rx="2"/><rect x="3" y="14" width="7" height="7" rx="2"/><rect x="14" y="14" width="7" height="7" rx="2"/>',
        audio: '<path d="M4 10v4M8 6v12M12 3v18M16 7v10M20 10v4"/>',
        mic: '<rect x="9" y="3" width="6" height="12" rx="3"/><path d="M6 10v2a6 6 0 0 0 12 0v-2M12 18v3M9 21h6"/>',
        translate: '<path d="M3 5h12M9 3v2M6 5c0 7 6 10 6 10M13 5c0 7-9 11-9 11M14 21l4-11 4 11M16 17h4"/>',
        subtitles: '<rect x="3" y="5" width="18" height="14" rx="3"/><path d="M7 10h10M7 14h4M14 14h3"/>',
        settings: '<path d="M4 6h16M4 12h16M4 18h16"/><rect x="7" y="4" width="3" height="4" rx="1"/><rect x="14" y="10" width="3" height="4" rx="1"/><rect x="8" y="16" width="3" height="4" rx="1"/>',
        play: '<path d="m8 5 11 7-11 7Z"/>',
        pause: '<path d="M8 5v14M16 5v14"/>',
        stop: '<rect x="6" y="6" width="12" height="12" rx="2"/>',
        refresh: '<path d="M20 7v5h-5M4 17v-5h5M6 7a7 7 0 0 1 12-1l2 6M4 12l2 6a7 7 0 0 0 12-1"/>',
        check: '<path d="m5 12 4 4 10-10"/>',
        close: '<path d="m6 6 12 12M18 6 6 18"/>',
        minus: '<path d="M5 12h14"/>',
        maximize: '<rect x="5" y="5" width="14" height="14" rx="2"/>',
        chevron: '<path d="m8 10 4 4 4-4"/>',
        arrow: '<path d="M5 12h14m-5-5 5 5-5 5"/>',
        folder: '<path d="M3 7V5h7l2 3h9v12H3Z"/>'
    })
    Image {
        anchors.centerIn: parent
        width: Math.min(root.width, root.sourceSize.width)
        height: Math.min(root.height, root.sourceSize.height)
        sourceSize: Qt.size(96, 96)
        fillMode: Image.PreserveAspectFit
        source: "data:image/svg+xml," + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="' + root.color + '" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round">' + (root.paths[root.name] || root.paths.overview) + '</svg>')
    }
}
