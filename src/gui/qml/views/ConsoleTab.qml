import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Controls.Material 2.15
import QtQuick.Layouts 1.15

Item {
    id: root
    property var themeObj: null
    property var t: themeObj

    // =========================================================
    // CONSOLE TAB
    // =========================================================
    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // Header
        Rectangle {
            Layout.fillWidth: true; implicitHeight: 68
            color: t ? t.bg2 : "#1a1a24"
            Rectangle { width: parent.width; height: 1; anchors.bottom: parent.bottom; color: t ? t.border1 : "#2e2e3e" }
            RowLayout {
                anchors { fill: parent; leftMargin: 28; rightMargin: 28 }
                spacing: t ? t.spaceMD : 12
                Text { text: "Console Log"; font.pixelSize: 20; font.bold: true; color: t ? t.textPrimary : "#f0f0ff" }
                Item { Layout.fillWidth: true }
                // Line count badge
                Rectangle {
                    Layout.alignment: Qt.AlignVCenter
                    implicitWidth: lineCountText.implicitWidth + 20; implicitHeight: 26; radius: 13
                    color: Qt.rgba(255,255,255,0.05)
                    border.color: t ? t.border2 : "#3d3d55"; border.width: 1
                    Text {
                        id: lineCountText; anchors.centerIn: parent
                        text: logModel.count + " lines"; font.pixelSize: 11
                        color: t ? t.textMuted : "#55556a"
                    }
                }
            }
        }

        // Log view
        Rectangle {
            Layout.fillWidth: true; Layout.fillHeight: true
            color: t ? t.bg2 : "#1a1a24"

            ListView {
                id: logList
                anchors { fill: parent; margins: 12; topMargin: 8 }
                model: ListModel { id: logModel }
                clip: true; spacing: 1
                verticalLayoutDirection: ListView.BottomToTop
                reuseItems: true
                cacheBuffer: 400

                property string filterLevel: "All Levels"

                delegate: Rectangle {
                    id: logDelegate
                    property bool matchesFilter: logList.filterLevel === "All Levels" || model.level === logList.filterLevel
                    width: logList.width
                    height: matchesFilter ? (logText.implicitHeight + 10) : 0
                    visible: matchesFilter
                    radius: 4
                    color: {
                        if (model.level === "ERROR")   return Qt.rgba(248, 113, 113, 0.08)
                        if (model.level === "WARNING") return Qt.rgba(250, 204, 21, 0.06)
                        return "transparent"
                    }

                    RowLayout {
                        anchors { fill: parent; leftMargin: 10; rightMargin: 10; topMargin: 5; bottomMargin: 5 }
                        spacing: 10
                        // Level dot
                        Rectangle {
                            width: 6; height: 6; radius: 3
                            Layout.alignment: Qt.AlignVCenter
                            color: {
                                if (model.level === "ERROR")   return t ? t.danger  : "#f87171"
                                if (model.level === "WARNING") return t ? t.warning : "#facc15"
                                if (model.level === "SUCCESS") return t ? t.success : "#4ade80"
                                return t ? t.textMuted : "#55556a"
                            }
                        }
                        // Level tag
                        Rectangle {
                            implicitWidth: lvlText.implicitWidth + 10; implicitHeight: 16; radius: 4
                            Layout.alignment: Qt.AlignVCenter
                            color: {
                                if (model.level === "ERROR")   return Qt.rgba(248, 113, 113, 0.15)
                                if (model.level === "WARNING") return Qt.rgba(250, 204, 21, 0.12)
                                if (model.level === "SUCCESS") return Qt.rgba(74, 222, 128, 0.12)
                                return Qt.rgba(255,255,255,0.05)
                            }
                            Text {
                                id: lvlText; anchors.centerIn: parent
                                text: model.level || "INFO"; font.pixelSize: 9; font.bold: true
                                color: {
                                    if (model.level === "ERROR")   return t ? t.danger  : "#f87171"
                                    if (model.level === "WARNING") return t ? t.warning : "#facc15"
                                    if (model.level === "SUCCESS") return t ? t.success : "#4ade80"
                                    return t ? t.textMuted : "#55556a"
                                }
                            }
                        }
                        Text {
                            id: logText; text: model.msg
                            font.pixelSize: t ? t.fontSizeSM : 12; font.family: "Consolas"
                            color: {
                                if (model.level === "ERROR")   return t ? t.danger   : "#f87171"
                                if (model.level === "WARNING") return t ? t.warning  : "#facc15"
                                if (model.level === "SUCCESS") return t ? t.success  : "#4ade80"
                                return t ? t.textSecondary : "#9090b8"
                            }
                            Layout.fillWidth: true; wrapMode: Text.WrapAnywhere
                        }
                    }
                }
                ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
            }
        }

        // Bottom toolbar
        Rectangle {
            Layout.fillWidth: true; implicitHeight: 48
            color: t ? t.bg3 : "#22222f"
            Rectangle { width: parent.width; height: 1; anchors.top: parent.top; color: t ? t.border1 : "#2e2e3e" }

            RowLayout {
                anchors { fill: parent; leftMargin: 16; rightMargin: 16 }
                spacing: t ? t.spaceSM : 8

                // Clear button
                Rectangle {
                    implicitWidth: 72; implicitHeight: 30; radius: 8
                    color: clrMouse.containsMouse ? Qt.rgba(255,255,255,0.06) : "transparent"
                    border.color: t ? t.border2 : "#3d3d55"; border.width: 1
                    Behavior on color { ColorAnimation { duration: 130 } }
                    Text { anchors.centerIn: parent; text: "Clear"; font.pixelSize: t ? t.fontSizeSM : 12; color: t ? t.textSecondary : "#9090b8" }
                    MouseArea {
                        id: clrMouse; anchors.fill: parent; hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor; onClicked: logModel.clear()
                    }
                }

                // Copy All button
                Rectangle {
                    id: copyBtn
                    implicitWidth: 88; implicitHeight: 30; radius: 8
                    color: copyMouse.containsMouse ? Qt.rgba(255,255,255,0.06) : "transparent"
                    border.color: t ? t.border2 : "#3d3d55"; border.width: 1
                    Behavior on color { ColorAnimation { duration: 130 } }

                    property bool justCopied: false

                    Text {
                        anchors.centerIn: parent
                        text: copyBtn.justCopied ? "✓ Copied!" : "📋 Copy All"
                        font.pixelSize: t ? t.fontSizeSM : 12
                        color: copyBtn.justCopied ? (t ? t.success : "#4ade80") : (t ? t.textSecondary : "#9090b8")
                        Behavior on color { ColorAnimation { duration: 200 } }
                    }

                    MouseArea {
                        id: copyMouse; anchors.fill: parent; hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            // Build full log text
                            var lines = []
                            for (var i = logModel.count - 1; i >= 0; i--) {
                                var entry = logModel.get(i)
                                lines.push("[" + (entry.level || "INFO") + "] " + entry.msg)
                            }
                            clipboardHelper.copyText(lines.join("\n"))
                            copyBtn.justCopied = true
                            copyResetTimer.restart()
                        }
                    }

                    Timer {
                        id: copyResetTimer; interval: 2000
                        onTriggered: copyBtn.justCopied = false
                    }
                }

                Item { Layout.fillWidth: true }

                // Auto-scroll toggle
                Text { text: "Auto-scroll"; font.pixelSize: t ? t.fontSizeSM : 12; color: t ? t.textMuted : "#55556a" }
                Rectangle {
                    id: autoScrollRect
                    width: 36; height: 20; radius: t ? t.radiusMD : 10
                    color: autoScrollRect.autoScroll ? (t ? t.accent : "#7c6cf8") : (t ? t.bg4 : "#2a2a3a")
                    Behavior on color { ColorAnimation { duration: 130 } }
                    property bool autoScroll: true

                    Rectangle {
                        width: 16; height: 16; radius: 8; anchors.verticalCenter: parent.verticalCenter
                        x: autoScrollRect.autoScroll ? parent.width - width - 2 : 2; color: "white"
                        Behavior on x { NumberAnimation { duration: 130; easing.type: Easing.OutQuad } }
                    }
                    MouseArea {
                        anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                        onClicked: autoScrollRect.autoScroll = !autoScrollRect.autoScroll
                    }
                }

                // Log level filter
                Rectangle {
                    implicitWidth: filterCombo.implicitWidth + 24; implicitHeight: 30; radius: 8
                    color: "transparent"
                    border.color: t ? t.border2 : "#3d3d55"; border.width: 1

                    ComboBox {
                        id: filterCombo
                        anchors.fill: parent
                        model: ["All Levels", "ERROR", "WARNING", "SUCCESS", "INFO"]
                        Material.theme: Material.Dark
                        background: Item {}
                        contentItem: Text {
                            leftPadding: 8; text: filterCombo.displayText
                            color: t ? t.textSecondary : "#9090b8"; font.pixelSize: 11
                            verticalAlignment: Text.AlignVCenter
                        }
                        onCurrentTextChanged: logList.filterLevel = currentText
                    }
                }
            }
        }
    }

    // Clipboard helper via hidden TextEdit
    TextEdit {
        id: clipboardHelper
        visible: false; width: 0; height: 0
        function copyText(txt) {
            text = txt
            selectAll()
            copy()
            text = ""
        }
    }

    Connections {
        target: appBackend
        function onLogEmitted(level, msg) {
            logModel.append({ "level": level, "msg": msg })
            if (logModel.count > 5000) logModel.remove(0)
            if (autoScrollRect.autoScroll) logList.positionViewAtBeginning()
        }
    }
}
