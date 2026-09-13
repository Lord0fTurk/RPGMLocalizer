import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Item {
    id: root
    property var themeObj: null
    property real value: 0.0     // 0.0 to 1.0
    property string statusText: ""
    property bool isIndeterminate: false

    implicitHeight: col.implicitHeight
    Layout.fillWidth: true

    ColumnLayout {
        id: col
        anchors.fill: parent
        spacing: 6

        RowLayout {
            Layout.fillWidth: true

            Text {
                text: root.statusText
                font.pixelSize: 12
                color: root.themeObj ? root.themeObj.textSecondary : "#9090b8"
                Layout.fillWidth: true
                elide: Text.ElideRight
            }

            Text {
                text: root.isIndeterminate ? "..." : Math.round(Math.max(0, Math.min(1.0, root.value)) * 100) + "%"
                font.pixelSize: 12
                font.bold: true
                color: root.themeObj ? root.themeObj.accentLight : "#a89bf9"
            }
        }

        // Track container
        Rectangle {
            id: track
            Layout.fillWidth: true
            height: 8
            radius: 4
            color: root.themeObj ? root.themeObj.bg4 : "#2a2a3a"
            clip: true

            // Active fill bar
            Rectangle {
                id: fillBar
                anchors.left: parent.left
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                radius: 4
                width: parent.width * Math.max(0.0, Math.min(1.0, root.value))

                gradient: Gradient {
                    orientation: Gradient.Horizontal
                    GradientStop { position: 0.0; color: root.themeObj ? root.themeObj.accentDark : "#5a4dd4" }
                    GradientStop { position: 1.0; color: root.themeObj ? root.themeObj.accent : "#7c6cf8" }
                }

                Behavior on width {
                    NumberAnimation { duration: 180; easing.type: Easing.OutQuad }
                }

                // Shimmer glow wave overlay
                Rectangle {
                    id: shimmerWave
                    width: 60
                    anchors.top: parent.top
                    anchors.bottom: parent.bottom
                    opacity: 0.45
                    gradient: Gradient {
                        orientation: Gradient.Horizontal
                        GradientStop { position: 0.0; color: "transparent" }
                        GradientStop { position: 0.5; color: "white" }
                        GradientStop { position: 1.0; color: "transparent" }
                    }

                    NumberAnimation on x {
                        from: -60
                        to: track.width
                        duration: 1400
                        loops: Animation.Infinite
                        running: root.value > 0.0 && root.value < 1.0 || root.isIndeterminate
                    }
                }
            }
        }
    }
}
