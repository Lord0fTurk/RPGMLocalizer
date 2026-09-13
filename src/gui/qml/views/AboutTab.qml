import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Item {
    id: root
    property var themeObj: null
    property var t: themeObj

    Item {
        anchors.centerIn: parent
        width: Math.min(parent.width - 80, 560)
        implicitHeight: mainCol.implicitHeight

        ColumnLayout {
            id: mainCol
            anchors.fill: parent
            spacing: 20

            // === Hero Card ===
            Rectangle {
                Layout.fillWidth: true
                implicitHeight: heroCol.implicitHeight + 48
                radius: 16
                color: t ? t.bg3 : "#22222f"
                border.color: t ? t.border1 : "#2e2e3e"
                border.width: 1

                // Top gradient stripe
                Rectangle {
                    width: parent.width; height: 3; radius: 1.5
                    anchors.top: parent.top; anchors.topMargin: 0
                    gradient: Gradient {
                        orientation: Gradient.Horizontal
                        GradientStop { position: 0.0; color: t ? t.accentDark : "#5a4dd4" }
                        GradientStop { position: 0.5; color: t ? t.accent     : "#7c6cf8" }
                        GradientStop { position: 1.0; color: t ? t.accentLight: "#a89bf9" }
                    }
                }

                ColumnLayout {
                    id: heroCol
                    anchors { fill: parent; margins: 24; topMargin: 28 }
                    spacing: 14

                    // Icon + Title row
                    RowLayout {
                        spacing: t ? t.spaceLG : 16

                        Rectangle {
                            width: 56; height: 56; radius: t ? t.radiusLG : 14
                            gradient: Gradient {
                                orientation: Gradient.Horizontal
                                GradientStop { position: 0.0; color: t ? t.accentDark : "#5a4dd4" }
                                GradientStop { position: 1.0; color: t ? t.accent     : "#7c6cf8" }
                            }
                            Image {
                                anchors.centerIn: parent
                                width: 38; height: 38
                                source: appBackend.appIconUrl
                                fillMode: Image.PreserveAspectFit
                                visible: appBackend.appIconUrl.length > 0
                                asynchronous: true
                                sourceSize.width: 76
                                sourceSize.height: 76
                            }
                            Text {
                                anchors.centerIn: parent
                                text: "⚡"
                                font.pixelSize: 28
                                visible: appBackend.appIconUrl.length === 0
                            }
                        }

                        ColumnLayout {
                            spacing: 3
                            Text {
                                text: "RPGMLocalizer"
                                font.pixelSize: 26; font.bold: true
                                color: t ? t.textPrimary : "#f0f0ff"
                            }
                            Text {
                                text: appBackend.appVersion + "  ·  Autonomous Localization Engine"
                                font.pixelSize: t ? t.fontSizeMD : 13
                                color: t ? t.textMuted : "#55556a"
                            }
                        }
                    }

                    Rectangle { Layout.fillWidth: true; height: 1; color: t ? t.border1 : "#2e2e3e" }

                    Text {
                        Layout.fillWidth: true
                        text: "High-performance translation and localization suite supporting Ruby RGSS 1/2/3 (.rxdata · .rvdata · .rvdata2) and MV/MZ JS (.json · .js) formats."
                        font.pixelSize: t ? t.fontSizeMD : 13
                        color: t ? t.textSecondary : "#9090b8"
                        wrapMode: Text.Wrap
                    }

                    // Tag row
                    RowLayout {
                        spacing: t ? t.spaceSM : 8
                        Repeater {
                            model: ["Python 3.12+", "PyQt6 + QML", "Segment-Safe", "GPL-3.0"]
                            delegate: Rectangle {
                                implicitHeight: 22; radius: 11
                                implicitWidth: tagLbl.implicitWidth + 16
                                color: Qt.rgba(124, 108, 248, 0.10)
                                border.color: Qt.rgba(124, 108, 248, 0.25)
                                border.width: 1
                                Text {
                                    id: tagLbl; anchors.centerIn: parent
                                    text: modelData; font.pixelSize: t ? t.fontSizeXS : 10
                                    color: t ? t.accentLight : "#a89bf9"
                                }
                            }
                        }
                        Item { Layout.fillWidth: true }
                    }
                }
            }

            // === Support Card ===
            Rectangle {
                Layout.fillWidth: true
                implicitHeight: supportCol.implicitHeight + 40
                radius: t ? t.radiusLG : 14
                color: Qt.rgba(124, 108, 248, 0.06)
                border.color: Qt.rgba(124, 108, 248, 0.2)
                border.width: 1

                ColumnLayout {
                    id: supportCol
                    anchors { fill: parent; margins: 20 }
                    spacing: 14

                    Text { text: "Support the Developer"; font.pixelSize: t ? t.fontSizeLG : 15; font.bold: true; color: t ? t.textPrimary : "#f0f0ff" }
                    Text {
                        text: "If this project has been useful to you, consider supporting it on Patreon."
                        font.pixelSize: t ? t.fontSizeMD : 13; color: t ? t.textSecondary : "#9090b8"
                        Layout.fillWidth: true; wrapMode: Text.Wrap
                    }

                    // Patreon Button
                    Rectangle {
                        Layout.fillWidth: true; implicitHeight: 42; radius: t ? t.radiusMD : 10
                        gradient: Gradient {
                            orientation: Gradient.Horizontal
                            GradientStop { position: 0.0; color: "#e85d04" }
                            GradientStop { position: 1.0; color: "#f48c06" }
                        }

                        Rectangle {
                            anchors.fill: parent; radius: parent.radius
                            color: patrMouse.containsMouse ? Qt.rgba(255,255,255,0.1) : "transparent"
                            Behavior on color { ColorAnimation { duration: 130 } }
                        }

                        RowLayout {
                            anchors.centerIn: parent; spacing: t ? t.spaceSM : 8
                            Text { text: "❤️"; font.pixelSize: 16 }
                            Text { text: "Support on Patreon"; color: "white"; font.pixelSize: 14; font.bold: true }
                        }

                        MouseArea {
                            id: patrMouse; anchors.fill: parent
                            hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                            onClicked: appBackend.openUrl("https://patreon.com/Lord0fTurk")
                        }
                    }
                }
            }

            // === Links Row ===
            RowLayout {
                Layout.fillWidth: true; spacing: t ? t.spaceMD : 12

                Repeater {
                    model: [
                        { icon: "📦", label: "GitHub",       url: "https://github.com/Lord0fTurk/RPGMLocalizer" },
                        { icon: "📘", label: "Documentation", url: "https://github.com/Lord0fTurk/RPGMLocalizer/wiki" },
                        { icon: "🐞", label: "Report a Bug",  url: "https://github.com/Lord0fTurk/RPGMLocalizer/issues" },
                    ]
                    delegate: Rectangle {
                        Layout.fillWidth: true; implicitHeight: 44; radius: t ? t.radiusMD : 10
                        color: linkMouse.containsMouse ? (t ? t.bgHover : "#32324a") : (t ? t.bg3 : "#22222f")
                        border.color: t ? t.border2 : "#3d3d55"; border.width: 1
                        Behavior on color { ColorAnimation { duration: 130 } }

                        RowLayout {
                            anchors.centerIn: parent; spacing: t ? t.spaceSM : 8
                            Text { text: modelData.icon; font.pixelSize: 14 }
                            Text { text: modelData.label; font.pixelSize: t ? t.fontSizeSM : 12; color: t ? t.textSecondary : "#9090b8" }
                        }
                        MouseArea {
                            id: linkMouse; anchors.fill: parent
                            hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                            onClicked: appBackend.openUrl(modelData.url)
                        }
                    }
                }
            }
        }
    }
}
