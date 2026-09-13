import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Popup {
    id: root
    property var themeObj: null
    property string title: "Warning"
    property string message: ""
    property string confirmText: "Confirm"
    property string cancelText: "Cancel"

    signal confirmed()
    signal cancelled()

    width: 420
    implicitHeight: dlgCol.implicitHeight + 48
    modal: true
    focus: true
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
    anchors.centerIn: parent

    background: Rectangle {
        radius: 14
        color: root.themeObj ? root.themeObj.bg2 : "#1a1a24"
        border.color: root.themeObj ? root.themeObj.border2 : "#3d3d55"
        border.width: 1
    }

    ColumnLayout {
        id: dlgCol
        anchors.fill: parent
        anchors.margins: 24
        spacing: 16

        RowLayout {
            spacing: 12
            Layout.fillWidth: true

            Rectangle {
                width: 32
                height: 32
                radius: 16
                color: Qt.rgba(250/255, 204/255, 21/255, 0.15)
                Text {
                    anchors.centerIn: parent
                    text: "⚠"
                    font.pixelSize: 16
                    color: "#facc15"
                }
            }

            Text {
                text: root.title
                font.pixelSize: 16
                font.bold: true
                color: root.themeObj ? root.themeObj.textPrimary : "#f0f0ff"
                Layout.fillWidth: true
            }
        }

        Text {
            text: root.message
            font.pixelSize: 13
            color: root.themeObj ? root.themeObj.textSecondary : "#9090b8"
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }

        Item { height: 4 }

        RowLayout {
            Layout.fillWidth: true
            spacing: 12

            Item { Layout.fillWidth: true }

            Rectangle {
                implicitWidth: 88
                implicitHeight: 34
                radius: 8
                color: "transparent"
                border.color: root.themeObj ? root.themeObj.border2 : "#3d3d55"
                border.width: 1

                Text {
                    anchors.centerIn: parent
                    text: root.cancelText
                    color: root.themeObj ? root.themeObj.textSecondary : "#9090b8"
                    font.pixelSize: 12
                }

                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        root.cancelled()
                        root.close()
                    }
                }
            }

            Rectangle {
                implicitWidth: 96
                implicitHeight: 34
                radius: 8
                color: root.themeObj ? root.themeObj.accent : "#7c6cf8"

                Text {
                    anchors.centerIn: parent
                    text: root.confirmText
                    color: "white"
                    font.pixelSize: 12
                    font.bold: true
                }

                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        root.confirmed()
                        root.close()
                    }
                }
            }
        }
    }
}
