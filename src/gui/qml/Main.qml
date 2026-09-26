import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Controls.Material 2.15
import QtQuick.Layouts 1.15
import QtQuick.Window 2.15

import "views"
import "components"

ApplicationWindow {
    id: window
    width: 1180
    height: 800
    minimumWidth: 960
    minimumHeight: 680
    visible: true
    title: "RPGMLocalizer"
    color: "#0d0d0f"

    Material.theme: Material.Dark
    Material.accent: "#7c6cf8"

    // === THEME TOKENS (single source of truth; inline QtObject avoids the
    //     need for a registered QML singleton module under QML 2.15) ===
    QtObject {
        id: theme
        readonly property color bg0:         "#0d0d0f"
        readonly property color bg1:         "#13131a"
        readonly property color bg2:         "#1a1a24"
        readonly property color bg3:         "#22222f"
        readonly property color bg4:         "#2a2a3a"
        readonly property color bgHover:     "#32324a"
        readonly property color bgActive:    "#3a3a55"
        readonly property color border1:     "#2e2e3e"
        readonly property color border2:     "#3d3d55"
        readonly property color border3:     "#5050aa"
        readonly property color accent:      "#7c6cf8"
        readonly property color accentLight: "#a89bf9"
        readonly property color accentDark:  "#5a4dd4"
        readonly property color accentGlow:  Qt.rgba(124, 108, 248, 0.15)
        readonly property color success:     "#4ade80"
        readonly property color warning:     "#facc15"
        readonly property color danger:      "#f87171"
        readonly property color info:        "#60a5fa"
        readonly property color textPrimary:   "#f0f0ff"
        readonly property color textSecondary: "#9090b8"
        readonly property color textMuted:     "#55556a"
        readonly property color textDisabled:  "#404055"

        // Typography scale
        readonly property int fontSizeXS:  10
        readonly property int fontSizeSM:  12
        readonly property int fontSizeMD:  13
        readonly property int fontSizeLG:  15
        readonly property int fontSizeXL:  18
        readonly property int fontSizeXXL: 24

        // 4/8/12px grid spacing scale
        readonly property int spaceXS:  4
        readonly property int spaceSM:  8
        readonly property int spaceMD:  12
        readonly property int spaceLG:  16
        readonly property int spaceXL:  24
        readonly property int spaceXXL: 32

        // Corner radii
        readonly property int radiusSM:  6
        readonly property int radiusMD:  10
        readonly property int radiusLG:  14
        readonly property int radiusXL:  20

        readonly property int animFast:   130
        readonly property int animMedium: 220
        readonly property int animSlow:   350
    }

    CompletionDialog {
        id: completionDialog
        themeObj: theme
        z: 10000
    }

    ToastNotification {
        id: toast
        themeObj: theme
        anchors.bottom: parent.bottom
        anchors.right: parent.right
        anchors.margins: 24
        z: 9999
    }

    Connections {
        target: appBackend
        function onFinished(success, summary) {
            window.show()
            window.raise()
            window.requestActivate()
            if (noticePopup.visible) {
                noticePopup.close()
            }
            completionDialog.openWith(success, summary, appBackend.projectPath)
        }
        function onInfoNotice(notice_type, title, message) {
            toast.show(notice_type, title, message)
            if (notice_type === "error" && !completionDialog.visible) {
                noticeTitle.text = title
                noticeMsg.text = message
                noticePopup.open()
            }
        }
    }

    Popup {
        id: noticePopup
        anchors.centerIn: parent
        width: 420
        height: noticeCol.implicitHeight + 48
        modal: true
        focus: true
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

        enter: Transition {
            NumberAnimation { property: "opacity"; from: 0.0; to: 1.0; duration: theme.animFast }
            NumberAnimation { property: "scale";   from: 0.92; to: 1.0; duration: theme.animFast; easing.type: Easing.OutQuad }
        }
        exit: Transition {
            NumberAnimation { property: "opacity"; from: 1.0; to: 0.0; duration: theme.animFast }
        }

        background: Rectangle {
            color: theme.bg3
            border.color: theme.border2
            border.width: 1
            radius: 14
            // Top accent stripe
            Rectangle {
                width: parent.width
                height: 3
                radius: 1.5
                color: theme.accent
                anchors.top: parent.top
            }
        }

        ColumnLayout {
            id: noticeCol
            anchors { left: parent.left; right: parent.right; top: parent.top; margins: 24 }
            spacing: 12

            Text {
                id: noticeTitle
                font.pixelSize: 16
                font.bold: true
                color: theme.textPrimary
            }
            Text {
                id: noticeMsg
                font.pixelSize: 13
                color: theme.textSecondary
                wrapMode: Text.Wrap
                textFormat: Text.RichText
                Layout.fillWidth: true
                onLinkActivated: function(link) {
                    if (typeof appBackend !== "undefined" && appBackend.openUrl) {
                        appBackend.openUrl(link)
                    } else {
                        Qt.openUrlExternally(link)
                    }
                }
            }
            Item { height: 4 }
            // OK Button
            Rectangle {
                Layout.alignment: Qt.AlignRight
                implicitWidth: 80
                implicitHeight: 34
                radius: 8
                color: okBtnMouse.pressed ? theme.accentDark : (okBtnMouse.containsMouse ? Qt.lighter(theme.accent, 1.1) : theme.accent)
                Behavior on color { ColorAnimation { duration: theme.animFast } }
                Text {
                    anchors.centerIn: parent
                    text: localeManager.strings.common.ok
                    color: "white"
                    font.pixelSize: 13
                    font.bold: true
                }
                MouseArea {
                    id: okBtnMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: noticePopup.close()
                }
            }
        }
    }

    // =========================================================
    // MAIN LAYOUT
    // =========================================================
    RowLayout {
        anchors.fill: parent
        spacing: 0

        // =====================================================
        // SIDEBAR
        // =====================================================
        Rectangle {
            Layout.fillHeight: true
            implicitWidth: 220
            color: theme.bg1

            // Right border
            Rectangle {
                width: 1
                height: parent.height
                anchors.right: parent.right
                color: theme.border1
            }

            ColumnLayout {
                anchors { fill: parent; margins: 0 }
                spacing: 0

                // --- Brand Header ---
                Rectangle {
                    Layout.fillWidth: true
                    implicitHeight: 70
                    color: "transparent"

                    RowLayout {
                        anchors { fill: parent; leftMargin: 16; rightMargin: 12 }
                        spacing: 12

                        // Brand Icon
                        Item {
                            width: 40; height: 40
                            Layout.alignment: Qt.AlignVCenter

                            // Subtle ambient glow behind the icon
                            Rectangle {
                                anchors.centerIn: parent
                                width: 40; height: 40
                                radius: 10
                                color: Qt.rgba(0, 240, 255, 0.08)
                                border.color: Qt.rgba(0, 240, 255, 0.25)
                                border.width: 1
                            }

                            Image {
                                anchors.centerIn: parent
                                width: 40; height: 40
                                source: appBackend.appIconUrl
                                fillMode: Image.PreserveAspectFit
                                mipmap: true
                                visible: appBackend.appIconUrl.length > 0
                                asynchronous: true
                                sourceSize.width: 80
                                sourceSize.height: 80
                            }

                            Text {
                                anchors.centerIn: parent
                                text: "⚡"
                                font.pixelSize: 20
                                visible: appBackend.appIconUrl.length === 0
                            }
                        }

                        // Brand Name & Version Tag
                        ColumnLayout {
                            spacing: 3
                            Layout.fillWidth: true
                            Layout.alignment: Qt.AlignVCenter

                            RowLayout {
                                spacing: 3
                                Text {
                                    text: "RPGM"
                                    font.pixelSize: 15
                                    font.bold: true
                                    font.letterSpacing: 0.5
                                    color: "#ffffff"
                                }
                                Text {
                                    text: "Localizer"
                                    font.pixelSize: 15
                                    font.bold: true
                                    font.letterSpacing: 0.3
                                    color: theme.accentLight
                                }
                            }

                            RowLayout {
                                spacing: 6

                                Rectangle {
                                    height: 16
                                    width: versionText.implicitWidth + 10
                                    radius: 8
                                    color: Qt.rgba(124, 108, 248, 0.16)
                                    border.color: Qt.rgba(124, 108, 248, 0.35)
                                    border.width: 1

                                    Text {
                                        id: versionText
                                        anchors.centerIn: parent
                                        text: appBackend.appVersion
                                        font.pixelSize: 9
                                        font.bold: true
                                        color: theme.accentLight
                                    }
                                }

                                Text {
                                    text: localeManager.strings.main.engine_tag
                                    font.pixelSize: 10
                                    color: theme.textMuted
                                }
                            }
                        }
                    }

                    // Bottom separator
                    Rectangle {
                        width: parent.width; height: 1
                        anchors.bottom: parent.bottom
                        color: theme.border1
                    }
                }

                // --- Nav Section label ---
                Text {
                    text: localeManager.strings.main.nav_section_label
                    font.pixelSize: 9
                    font.bold: true
                    font.letterSpacing: 1.2
                    color: theme.textMuted
                    leftPadding: 20
                    topPadding: 16
                    bottomPadding: 6
                }

                // --- Nav Items ---
                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.leftMargin: 10
                    Layout.rightMargin: 10
                    spacing: 2

                    Repeater {
                        model: [
                            { icon: "⚡", label: localeManager.strings.main.nav_auto_translate, idx: 0 },
                            { icon: "✏️", label: localeManager.strings.main.nav_editor,          idx: 1 },
                            { icon: "⚙",  label: localeManager.strings.main.nav_settings,        idx: 2 },
                            { icon: "📦", label: localeManager.strings.main.nav_data,             idx: 3 },
                            { icon: "📋", label: localeManager.strings.main.nav_console,          idx: 4 },
                        ]

                        delegate: Item {
                            Layout.fillWidth: true
                            height: 42

                            property bool isActive: stackLayout.currentIndex === modelData.idx

                            // Active glow bg
                            Rectangle {
                                anchors.fill: parent
                                radius: 8
                                color: isActive ? theme.accentGlow : (navMouse.containsMouse ? Qt.rgba(255,255,255,0.04) : "transparent")
                                Behavior on color { ColorAnimation { duration: theme.animFast } }
                            }

                            // Active left indicator bar
                            Rectangle {
                                width: 3; height: 22; radius: 1.5
                                anchors { left: parent.left; leftMargin: 0; verticalCenter: parent.verticalCenter }
                                color: theme.accent
                                opacity: isActive ? 1.0 : 0.0
                                Behavior on opacity { NumberAnimation { duration: theme.animFast } }
                            }

                            RowLayout {
                                anchors { fill: parent; leftMargin: 14; rightMargin: 10 }
                                spacing: 10

                                Text {
                                    text: modelData.icon
                                    font.pixelSize: 15
                                    opacity: isActive ? 1.0 : 0.6
                                    Behavior on opacity { NumberAnimation { duration: theme.animFast } }
                                }
                                Text {
                                    text: modelData.label
                                    font.pixelSize: 13
                                    font.bold: isActive
                                    color: isActive ? theme.textPrimary : theme.textSecondary
                                    Behavior on color { ColorAnimation { duration: theme.animFast } }
                                }
                            }

                            MouseArea {
                                id: navMouse
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: stackLayout.currentIndex = modelData.idx
                            }
                        }
                    }
                }

                Item { Layout.fillHeight: true }

                // --- Bottom: About + version tag ---
                Rectangle {
                    Layout.fillWidth: true
                    height: 1
                    color: theme.border1
                }

                Item {
                    id: aboutItem
                    Layout.fillWidth: true
                    height: 50

                    property bool isActive: stackLayout.currentIndex === 5

                    Rectangle {
                        anchors.fill: parent
                        anchors.margins: 10
                        radius: 8
                        color: aboutItem.isActive ? theme.accentGlow : (aboutMouse.containsMouse ? Qt.rgba(255,255,255,0.04) : "transparent")
                        Behavior on color { ColorAnimation { duration: theme.animFast } }
                    }

                    RowLayout {
                        anchors { fill: parent; leftMargin: 24; rightMargin: 16 }
                        spacing: 10
                        Text { text: "ℹ️"; font.pixelSize: 14 }
                        Text {
                            text: localeManager.strings.main.nav_about
                            font.pixelSize: 13
                            color: aboutItem.isActive ? theme.textPrimary : theme.textSecondary
                            Behavior on color { ColorAnimation { duration: theme.animFast } }
                        }
                    }

                    MouseArea {
                        id: aboutMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: stackLayout.currentIndex = 5
                    }
                }
            }
        }

        // =====================================================
        // CONTENT AREA
        // =====================================================
        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: theme.bg2

            StackLayout {
                id: stackLayout
                anchors.fill: parent
                currentIndex: 0

                // Lazily instantiate the less-frequently-visited tabs on first
                // visit (Loader.active latches true and never resets to false,
                // so state entered by the user is preserved on tab switches).
                // Home (default tab) and Console (must keep listening for
                // log_message signals from app startup, or early log lines
                // would be silently lost) are kept eager.
                property bool editorVisited: false
                property bool settingsVisited: false
                property bool dataVisited: false
                property bool aboutVisited: false

                onCurrentIndexChanged: {
                    if (currentIndex === 1) editorVisited = true
                    else if (currentIndex === 2) settingsVisited = true
                    else if (currentIndex === 3) dataVisited = true
                    else if (currentIndex === 5) aboutVisited = true
                }

                HomeTab { themeObj: theme }

                Loader {
                    active: stackLayout.editorVisited
                    asynchronous: true
                    sourceComponent: Component { EditorTab { themeObj: theme } }
                }

                Loader {
                    active: stackLayout.settingsVisited
                    asynchronous: true
                    sourceComponent: Component { SettingsTab { themeObj: theme } }
                }
                Loader {
                    active: stackLayout.dataVisited
                    asynchronous: true
                    sourceComponent: Component { DataTab { themeObj: theme } }
                }

                ConsoleTab { themeObj: theme }

                Loader {
                    active: stackLayout.aboutVisited
                    asynchronous: true
                    sourceComponent: Component { AboutTab { themeObj: theme } }
                }
            }
        }
    }
}
