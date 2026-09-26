import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Item {
    id: root
    property var themeObj: null
    property var t: themeObj

    Item {
        anchors.centerIn: parent
        width: Math.min(parent.width - 80, 640)
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

                        Item {
                            width: 64; height: 64

                            // Ambient glow behind logo
                            Rectangle {
                                anchors.centerIn: parent
                                width: 64; height: 64
                                radius: 16
                                color: Qt.rgba(0, 240, 255, 0.08)
                                border.color: Qt.rgba(0, 240, 255, 0.25)
                                border.width: 1
                            }

                            Image {
                                anchors.centerIn: parent
                                width: 64; height: 64
                                source: appBackend.appIconUrl
                                fillMode: Image.PreserveAspectFit
                                mipmap: true
                                visible: appBackend.appIconUrl.length > 0
                                asynchronous: true
                                sourceSize.width: 128
                                sourceSize.height: 128
                            }

                            Text {
                                anchors.centerIn: parent
                                text: "⚡"
                                font.pixelSize: 32
                                visible: appBackend.appIconUrl.length === 0
                            }
                        }

                        ColumnLayout {
                            spacing: 5

                            RowLayout {
                                spacing: 4
                                Text {
                                    text: "RPGM"
                                    font.pixelSize: 26
                                    font.bold: true
                                    font.letterSpacing: 0.5
                                    color: t ? t.textPrimary : "#ffffff"
                                }
                                Text {
                                    text: "Localizer"
                                    font.pixelSize: 26
                                    font.bold: true
                                    font.letterSpacing: 0.5
                                    color: t ? t.accentLight : "#a89bf9"
                                }
                            }

                            RowLayout {
                                spacing: 8

                                Rectangle {
                                    height: 20
                                    width: aboutVersionText.implicitWidth + 12
                                    radius: 10
                                    color: Qt.rgba(124, 108, 248, 0.16)
                                    border.color: Qt.rgba(124, 108, 248, 0.35)
                                    border.width: 1

                                    Text {
                                        id: aboutVersionText
                                        anchors.centerIn: parent
                                        text: appBackend.appVersion
                                        font.pixelSize: 11
                                        font.bold: true
                                        color: t ? t.accentLight : "#a89bf9"
                                    }
                                }

                                Text {
                                    text: localeManager.strings.about.tagline
                                    font.pixelSize: t ? t.fontSizeMD : 13
                                    color: t ? t.textMuted : "#55556a"
                                }
                            }
                        }
                    }

                    Rectangle { Layout.fillWidth: true; height: 1; color: t ? t.border1 : "#2e2e3e" }

                    Text {
                        Layout.fillWidth: true
                        text: localeManager.strings.about.description
                        font.pixelSize: t ? t.fontSizeMD : 13
                        color: t ? t.textSecondary : "#9090b8"
                        wrapMode: Text.Wrap
                    }

                    // Tag row
                    RowLayout {
                        spacing: t ? t.spaceSM : 8
                        Repeater {
                            model: [
                                localeManager.strings.about.tag_python,
                                localeManager.strings.about.tag_pyqt,
                                localeManager.strings.about.tag_segment_safe,
                                localeManager.strings.about.tag_license,
                            ]
                            delegate: Rectangle {
                                implicitHeight: 24; radius: 12
                                implicitWidth: tagLbl.implicitWidth + 16
                                color: Qt.rgba(124, 108, 248, 0.10)
                                border.color: Qt.rgba(124, 108, 248, 0.25)
                                border.width: 1
                                Text {
                                    id: tagLbl; anchors.centerIn: parent
                                    text: modelData; font.pixelSize: 11
                                    font.bold: true
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
                implicitHeight: supportCol.implicitHeight + 36
                radius: 14
                color: Qt.rgba(124, 108, 248, 0.05)
                border.color: Qt.rgba(124, 108, 248, 0.20)
                border.width: 1

                ColumnLayout {
                    id: supportCol
                    anchors { fill: parent; margins: 20 }
                    spacing: 12

                    RowLayout {
                        spacing: 8
                        Text { text: "❤️"; font.pixelSize: 15 }
                        Text { text: localeManager.strings.about.support_title; font.pixelSize: 14; font.bold: true; color: t ? t.textPrimary : "#f0f0ff" }
                    }

                    Text {
                        text: localeManager.strings.about.support_desc
                        font.pixelSize: 12; color: t ? t.textSecondary : "#9090b8"
                        Layout.fillWidth: true; wrapMode: Text.Wrap
                    }

                    // Refined Patreon Button
                    Rectangle {
                        Layout.alignment: Qt.AlignHCenter
                        implicitWidth: 260; implicitHeight: 38; radius: 9
                        gradient: Gradient {
                            orientation: Gradient.Horizontal
                            GradientStop { position: 0.0; color: "#e85d04" }
                            GradientStop { position: 1.0; color: "#f48c06" }
                        }

                        Rectangle {
                            anchors.fill: parent; radius: parent.radius
                            color: patrMouse.containsMouse ? Qt.rgba(255,255,255,0.12) : "transparent"
                            Behavior on color { ColorAnimation { duration: 130 } }
                        }

                        RowLayout {
                            anchors.centerIn: parent; spacing: 8
                            Text { text: "☕"; font.pixelSize: 13 }
                            Text { text: localeManager.strings.about.patreon_button; color: "white"; font.pixelSize: 13; font.bold: true }
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
                        { icon: "📦", label: localeManager.strings.about.link_github, url: "https://github.com/Lord0fTurk/RPGMLocalizer" },
                        { icon: "📘", label: localeManager.strings.about.link_docs,   url: "https://github.com/Lord0fTurk/RPGMLocalizer/wiki" },
                        { icon: "🐞", label: localeManager.strings.about.link_bug,    url: "https://github.com/Lord0fTurk/RPGMLocalizer/issues" },
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
