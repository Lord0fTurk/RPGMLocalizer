import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Item {
    id: root
    property var themeObj: null
    property string noticeType: "info" // info, success, warning, error
    property string title: ""
    property string message: ""
    property int durationMs: 3500

    width: 380
    implicitHeight: contentCol.implicitHeight + 24
    opacity: 0.0
    visible: opacity > 0.0

    function show(typeStr, titleStr, messageStr) {
        noticeType = typeStr || "info"
        title = titleStr || ""
        message = messageStr || ""
        showAnim.restart()
        autoHideTimer.restart()
    }

    function hide() {
        hideAnim.restart()
    }

    Timer {
        id: autoHideTimer
        interval: root.durationMs
        repeat: false
        onTriggered: root.hide()
    }

    Rectangle {
        id: bgCard
        anchors.fill: parent
        radius: 10
        color: root.themeObj ? root.themeObj.bg2 : "#1a1a24"
        border.width: 1
        border.color: {
            if (root.noticeType === "success") return "#4ade80"
            if (root.noticeType === "warning") return "#facc15"
            if (root.noticeType === "error")   return "#f87171"
            return root.themeObj ? root.themeObj.accent : "#7c6cf8"
        }

        // Accent indicator strip
        Rectangle {
            id: indicatorStrip
            width: 4
            anchors.left: parent.left
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            radius: 2
            color: bgCard.border.color
        }

        ColumnLayout {
            id: contentCol
            anchors.fill: parent
            anchors.leftMargin: 16
            anchors.rightMargin: 16
            anchors.topMargin: 12
            anchors.bottomMargin: 12
            spacing: 4

            RowLayout {
                Layout.fillWidth: true

                Text {
                    id: txtTitle
                    text: root.title
                    font.pixelSize: 13
                    font.bold: true
                    color: root.themeObj ? root.themeObj.textPrimary : "#f0f0ff"
                    Layout.fillWidth: true
                }

                Text {
                    text: "✕"
                    font.pixelSize: 11
                    color: root.themeObj ? root.themeObj.textMuted : "#55556a"
                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: root.hide()
                    }
                }
            }

            Text {
                id: txtMsg
                text: root.message
                font.pixelSize: 12
                color: root.themeObj ? root.themeObj.textSecondary : "#9090b8"
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
        }
    }

    transform: Translate {
        id: toastTrans
        y: 0
    }

    ParallelAnimation {
        id: showAnim
        NumberAnimation { target: root; property: "opacity"; from: 0.0; to: 1.0; duration: 200; easing.type: Easing.OutQuad }
        NumberAnimation { target: toastTrans; property: "y"; from: 12; to: 0; duration: 200; easing.type: Easing.OutQuad }
    }

    ParallelAnimation {
        id: hideAnim
        NumberAnimation { target: root; property: "opacity"; from: 1.0; to: 0.0; duration: 200; easing.type: Easing.InQuad }
        NumberAnimation { target: toastTrans; property: "y"; from: 0; to: -8; duration: 200; easing.type: Easing.InQuad }
    }
}
