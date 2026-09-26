import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Controls.Material 2.15
import QtQuick.Layouts 1.15

import "../js/I18n.js" as I18n

Item {
    id: root
    property var themeObj: null
    property var t: themeObj
    property string searchQuery: ""
    readonly property var filterCodes: ["All Levels", "ERROR", "WARNING", "SUCCESS", "INFO"]
    readonly property var filterLabels: [
        localeManager.strings.console.filter_all, "ERROR", "WARNING", "SUCCESS", "INFO"
    ]

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
                spacing: t ? t.spaceMD : 14
                Text { text: localeManager.strings.console.title; font.pixelSize: 20; font.bold: true; color: t ? t.textPrimary : "#f0f0ff" }
                Item { Layout.fillWidth: true }

                // Live search bar
                Rectangle {
                    implicitWidth: 240; implicitHeight: 32; radius: 8
                    color: t ? t.bg4 : "#2a2a3a"
                    border.color: searchInput.activeFocus ? (t ? t.accent : "#7c6cf8") : (t ? t.border2 : "#3d3d55")
                    border.width: 1

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 10; anchors.rightMargin: 8
                        spacing: 6
                        Text { text: "🔍"; font.pixelSize: 11; opacity: 0.7 }
                        TextField {
                            id: searchInput
                            Layout.fillWidth: true
                            placeholderText: localeManager.strings.console.search_placeholder
                            color: t ? t.textPrimary : "#f0f0ff"
                            placeholderTextColor: t ? t.textMuted : "#55556a"
                            font.pixelSize: 11
                            background: Item {}
                            onTextChanged: root.searchQuery = text
                        }
                        Text {
                            visible: searchInput.text.length > 0
                            text: "✕"; font.pixelSize: 10; color: t ? t.textMuted : "#55556a"
                            MouseArea {
                                anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                                onClicked: searchInput.text = ""
                            }
                        }
                    }
                }

                // Line count badge
                Rectangle {
                    Layout.alignment: Qt.AlignVCenter
                    implicitWidth: lineCountText.implicitWidth + 20; implicitHeight: 28; radius: 14
                    color: Qt.rgba(255,255,255,0.05)
                    border.color: t ? t.border2 : "#3d3d55"; border.width: 1
                    Text {
                        id: lineCountText; anchors.centerIn: parent
                        text: I18n.format(localeManager.strings.console.line_count, {count: logModel.count}); font.pixelSize: 11
                        color: t ? t.textMuted : "#55556a"
                    }
                }
            }
        }

        // Log view
        Rectangle {
            Layout.fillWidth: true; Layout.fillHeight: true
            color: t ? t.bg2 : "#1a1a24"

            // Empty State
            ColumnLayout {
                anchors.centerIn: parent
                spacing: 12
                visible: logModel.count === 0

                Rectangle {
                    Layout.alignment: Qt.AlignHCenter
                    width: 56; height: 56; radius: 16
                    color: Qt.rgba(255, 255, 255, 0.04)
                    border.color: t ? t.border1 : "#2e2e3e"
                    border.width: 1
                    Text { anchors.centerIn: parent; text: "⚡"; font.pixelSize: 24 }
                }
                Text {
                    Layout.alignment: Qt.AlignHCenter
                    text: localeManager.strings.console.empty_title
                    font.pixelSize: 15; font.bold: true
                    color: t ? t.textSecondary : "#9090b8"
                }
                Text {
                    Layout.alignment: Qt.AlignHCenter
                    text: localeManager.strings.console.empty_desc
                    font.pixelSize: 12
                    color: t ? t.textMuted : "#55556a"
                }
            }

            ListView {
                id: logList
                anchors { fill: parent; margins: 12; topMargin: 8 }
                model: ListModel { id: logModel }
                clip: true; spacing: 2
                reuseItems: true
                cacheBuffer: 400

                property string filterLevel: "All Levels"

                delegate: Rectangle {
                    id: logDelegate
                    property bool matchesFilter: (logList.filterLevel === "All Levels" || model.level === logList.filterLevel) &&
                                                 (root.searchQuery === "" || (model.msg && model.msg.toLowerCase().indexOf(root.searchQuery.toLowerCase()) !== -1))
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

                        // Timestamp
                        Text {
                            text: model.time || ""
                            font.pixelSize: 10; font.family: "Consolas"
                            color: t ? t.textMuted : "#55556a"
                            Layout.alignment: Qt.AlignVCenter
                        }

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
                            implicitWidth: lvlText.implicitWidth + 10; implicitHeight: 18; radius: 4
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

                        // Message Text
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
                    Text { anchors.centerIn: parent; text: localeManager.strings.console.clear_button; font.pixelSize: t ? t.fontSizeSM : 12; color: t ? t.textSecondary : "#9090b8" }
                    MouseArea {
                        id: clrMouse; anchors.fill: parent; hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor; onClicked: logModel.clear()
                    }
                }

                // Copy All button
                Rectangle {
                    id: copyBtn
                    implicitWidth: 96; implicitHeight: 30; radius: 8
                    color: copyMouse.containsMouse ? Qt.rgba(255,255,255,0.06) : "transparent"
                    border.color: t ? t.border2 : "#3d3d55"; border.width: 1
                    Behavior on color { ColorAnimation { duration: 130 } }

                    property bool justCopied: false

                    Text {
                        anchors.centerIn: parent
                        text: copyBtn.justCopied ? localeManager.strings.console.copied_label : localeManager.strings.console.copy_all_label
                        font.pixelSize: t ? t.fontSizeSM : 12
                        color: copyBtn.justCopied ? (t ? t.success : "#4ade80") : (t ? t.textSecondary : "#9090b8")
                        Behavior on color { ColorAnimation { duration: 200 } }
                    }

                    MouseArea {
                        id: copyMouse; anchors.fill: parent; hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            var lines = []
                            for (var i = 0; i < logModel.count; i++) {
                                var entry = logModel.get(i)
                                var tStr = entry.time ? ("[" + entry.time + "] ") : ""
                                lines.push(tStr + "[" + (entry.level || "INFO") + "] " + entry.msg)
                            }
                            appBackend.copyToClipboard(lines.join("\n"))
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
                Text { text: localeManager.strings.console.auto_scroll_label; font.pixelSize: t ? t.fontSizeSM : 12; color: t ? t.textMuted : "#55556a" }
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
                        model: root.filterLabels
                        Material.theme: Material.Dark
                        background: Item {}
                        contentItem: Text {
                            leftPadding: 8; text: filterCombo.displayText
                            color: t ? t.textSecondary : "#9090b8"; font.pixelSize: 11
                            verticalAlignment: Text.AlignVCenter
                        }
                        onActivated: (index) => { logList.filterLevel = root.filterCodes[index] }
                    }
                }
            }
        }
    }

    Connections {
        target: appBackend
        function onLogEmitted(level, msg) {
            var now = new Date()
            var timeStr = ("0" + now.getHours()).slice(-2) + ":" +
                          ("0" + now.getMinutes()).slice(-2) + ":" +
                          ("0" + now.getSeconds()).slice(-2)
            logModel.append({ "level": level, "msg": msg, "time": timeStr })
            if (logModel.count > 5000) logModel.remove(0)
            if (autoScrollRect.autoScroll) logList.positionViewAtEnd()
        }
    }
}
