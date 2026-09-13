import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Popup {
    id: root
    property var themeObj: null
    property bool isSuccess: true
    property string summaryText: ""
    property string projectPath: ""

    signal openedFolder()

    function openWith(success, summary, projPath) {
        root.isSuccess = success
        root.summaryText = summary || ""
        root.projectPath = projPath || ""
        root.open()
    }

    width: 480
    implicitHeight: contentCol.implicitHeight + 48
    modal: true
    focus: true
    dim: true
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
    anchors.centerIn: parent

    enter: Transition {
        NumberAnimation { property: "opacity"; from: 0.0; to: 1.0; duration: root.themeObj ? root.themeObj.animFast : 150 }
        NumberAnimation { property: "scale"; from: 0.92; to: 1.0; duration: root.themeObj ? root.themeObj.animFast : 150; easing.type: Easing.OutQuad }
    }
    exit: Transition {
        NumberAnimation { property: "opacity"; from: 1.0; to: 0.0; duration: root.themeObj ? root.themeObj.animFast : 150 }
        NumberAnimation { property: "scale"; from: 1.0; to: 0.95; duration: root.themeObj ? root.themeObj.animFast : 150; easing.type: Easing.InQuad }
    }

    background: Rectangle {
        radius: 16
        color: root.themeObj ? root.themeObj.bg2 : "#1a1a24"
        border.color: root.isSuccess ? (root.themeObj ? root.themeObj.success : "#4ade80") : (root.themeObj ? root.themeObj.danger : "#f87171")
        border.width: 1

        // Top decorative accent line
        Rectangle {
            width: parent.width - 32
            height: 3
            radius: 1.5
            color: root.isSuccess ? (root.themeObj ? root.themeObj.success : "#4ade80") : (root.themeObj ? root.themeObj.danger : "#f87171")
            anchors.top: parent.top
            anchors.horizontalCenter: parent.horizontalCenter
        }
    }

    ColumnLayout {
        id: contentCol
        anchors.fill: parent
        anchors.margins: 24
        spacing: 16

        // Header with status badge
        RowLayout {
            spacing: 14
            Layout.fillWidth: true

            Rectangle {
                width: 46
                height: 46
                radius: 23
                color: root.isSuccess ? Qt.rgba(74/255, 222/255, 128/255, 0.15) : Qt.rgba(248/255, 113/255, 113/255, 0.15)
                border.color: root.isSuccess ? Qt.rgba(74/255, 222/255, 128/255, 0.35) : Qt.rgba(248/255, 113/255, 113/255, 0.35)
                border.width: 1

                Text {
                    anchors.centerIn: parent
                    text: root.isSuccess ? "✔" : "✕"
                    font.pixelSize: 22
                    font.bold: true
                    color: root.isSuccess ? "#4ade80" : "#f87171"
                }
            }

            ColumnLayout {
                spacing: 3
                Layout.fillWidth: true

                Text {
                    text: root.isSuccess ? "Translation Completed!" : "Operation Failed"
                    font.pixelSize: 17
                    font.bold: true
                    color: root.themeObj ? root.themeObj.textPrimary : "#f0f0ff"
                }

                Text {
                    text: root.isSuccess
                          ? "Game texts have been successfully translated and saved."
                          : "An issue occurred during the translation process."
                    font.pixelSize: 12
                    color: root.themeObj ? root.themeObj.textSecondary : "#9090b8"
                }
            }
        }

        // Summary Card
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: summaryCol.implicitHeight + 24
            radius: 10
            color: root.themeObj ? root.themeObj.bg3 : "#22222f"
            border.color: root.themeObj ? root.themeObj.border1 : "#2e2e3e"
            border.width: 1

            ColumnLayout {
                id: summaryCol
                anchors.fill: parent
                anchors.margins: 12
                spacing: 8

                RowLayout {
                    spacing: 8
                    Layout.fillWidth: true

                    Text {
                        text: root.isSuccess ? "📊" : "⚠"
                        font.pixelSize: 14
                    }

                    Text {
                        text: root.summaryText || (root.isSuccess ? "Project successfully translated." : "An error occurred.")
                        font.pixelSize: 13
                        font.bold: true
                        color: root.themeObj ? root.themeObj.textPrimary : "#f0f0ff"
                        wrapMode: Text.Wrap
                        Layout.fillWidth: true
                    }
                }

                RowLayout {
                    visible: root.projectPath.length > 0
                    spacing: 8
                    Layout.fillWidth: true

                    Text {
                        text: "📂"
                        font.pixelSize: 13
                    }

                    Text {
                        text: root.projectPath ? root.projectPath.split(/[/\\\\]/).pop() : ""
                        font.pixelSize: 12
                        font.family: "Consolas, monospace"
                        color: root.themeObj ? root.themeObj.accentLight : "#a89bf9"
                        elide: Text.ElideMiddle
                        Layout.fillWidth: true
                    }
                }
            }
        }

        Item { height: 4 }

        // Action Buttons Row
        RowLayout {
            Layout.fillWidth: true
            spacing: 12

            // Open Folder button (if projectPath available)
            Rectangle {
                visible: root.projectPath.length > 0
                implicitWidth: 140
                implicitHeight: 36
                radius: 8
                color: folderBtnMouse.pressed
                       ? (root.themeObj ? root.themeObj.bgActive : "#3a3a55")
                       : (folderBtnMouse.containsMouse ? (root.themeObj ? root.themeObj.bgHover : "#32324a") : (root.themeObj ? root.themeObj.bg4 : "#2a2a3a"))
                border.color: root.themeObj ? root.themeObj.border2 : "#3d3d55"
                border.width: 1

                RowLayout {
                    anchors.centerIn: parent
                    spacing: 6
                    Text { text: "📁"; font.pixelSize: 12 }
                    Text {
                        text: "Open Folder"
                        color: root.themeObj ? root.themeObj.textPrimary : "#f0f0ff"
                        font.pixelSize: 12
                        font.bold: true
                    }
                }

                MouseArea {
                    id: folderBtnMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        root.openedFolder()
                        if (typeof appBackend !== "undefined" && appBackend.openProjectFolder) {
                            appBackend.openProjectFolder()
                        }
                    }
                }
            }

            Item { Layout.fillWidth: true }

            // OK / Close Button
            Rectangle {
                implicitWidth: 100
                implicitHeight: 36
                radius: 8
                color: okBtnMouse.pressed
                       ? (root.themeObj ? root.themeObj.accentDark : "#5a4dd4")
                       : (okBtnMouse.containsMouse ? Qt.lighter(root.themeObj ? root.themeObj.accent : "#7c6cf8", 1.1) : (root.themeObj ? root.themeObj.accent : "#7c6cf8"))
                Behavior on color { ColorAnimation { duration: root.themeObj ? root.themeObj.animFast : 130 } }

                Text {
                    anchors.centerIn: parent
                    text: "OK"
                    color: "white"
                    font.pixelSize: 13
                    font.bold: true
                }

                MouseArea {
                    id: okBtnMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.close()
                }
            }
        }
    }
}
