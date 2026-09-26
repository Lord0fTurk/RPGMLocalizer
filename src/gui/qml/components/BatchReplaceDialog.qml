import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Popup {
    id: root
    property var themeObj: null
    property var t: themeObj
    property string activeFileName: "all"

    signal replaceRequested(string search, string replace, string fileScope, bool matchCase)

    parent: Overlay.overlay
    anchors.centerIn: parent
    width: 460
    height: contentCol.implicitHeight + 48
    modal: true
    focus: true
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

    background: Rectangle {
        color: t ? t.bg3 : "#22222f"
        border.color: t ? t.border2 : "#3d3d55"
        border.width: 1
        radius: 14

        Rectangle {
            width: parent.width; height: 3; radius: 1.5
            color: t ? t.accent : "#7c6cf8"
            anchors.top: parent.top
        }
    }

    ColumnLayout {
        id: contentCol
        anchors { left: parent.left; right: parent.right; top: parent.top; margins: 24 }
        spacing: 16

        RowLayout {
            Layout.fillWidth: true
            Text {
                text: localeManager.strings.batch_replace.title
                font.pixelSize: 16
                font.bold: true
                color: t ? t.textPrimary : "#ffffff"
            }
            Item { Layout.fillWidth: true }
            Text {
                text: "✕"
                font.pixelSize: 14
                color: t ? t.textMuted : "#777790"
                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.close()
                }
            }
        }

        Text {
            text: localeManager.strings.batch_replace.safety_note
            font.pixelSize: 11
            color: t ? t.textSecondary : "#9a9ab2"
            wrapMode: Text.Wrap
            Layout.fillWidth: true
        }

        // Search Field
        ColumnLayout {
            Layout.fillWidth: true; spacing: 4
            Text { text: localeManager.strings.batch_replace.search_label; font.pixelSize: 12; color: t ? t.textSecondary : "#bbbbd0" }
            Rectangle {
                Layout.fillWidth: true; height: 36; radius: 8
                color: t ? t.bg2 : "#1a1a24"
                border.color: searchInput.activeFocus ? (t ? t.accent : "#7c6cf8") : (t ? t.border1 : "#2e2e3e")
                TextInput {
                    id: searchInput
                    anchors { fill: parent; leftMargin: 10; rightMargin: 10 }
                    verticalAlignment: TextInput.AlignVCenter
                    color: t ? t.textPrimary : "#ffffff"
                    font.pixelSize: 13
                    selectByMouse: true
                }
            }
        }

        // Replace Field
        ColumnLayout {
            Layout.fillWidth: true; spacing: 4
            Text { text: localeManager.strings.batch_replace.replace_label; font.pixelSize: 12; color: t ? t.textSecondary : "#bbbbd0" }
            Rectangle {
                Layout.fillWidth: true; height: 36; radius: 8
                color: t ? t.bg2 : "#1a1a24"
                border.color: replaceInput.activeFocus ? (t ? t.accent : "#7c6cf8") : (t ? t.border1 : "#2e2e3e")
                TextInput {
                    id: replaceInput
                    anchors { fill: parent; leftMargin: 10; rightMargin: 10 }
                    verticalAlignment: TextInput.AlignVCenter
                    color: t ? t.textPrimary : "#ffffff"
                    font.pixelSize: 13
                    selectByMouse: true
                }
            }
        }

        // Scope Selector
        RowLayout {
            spacing: 20
            Layout.fillWidth: true

            CheckBox {
                id: matchCaseCheck
                text: localeManager.strings.batch_replace.match_case_label
                contentItem: Text {
                    text: matchCaseCheck.text
                    font.pixelSize: 12
                    color: t ? t.textPrimary : "#ffffff"
                    leftPadding: matchCaseCheck.indicator.width + 6
                    verticalAlignment: Text.AlignVCenter
                }
            }

            CheckBox {
                id: currentFileOnlyCheck
                text: localeManager.strings.batch_replace.current_file_only_label
                enabled: root.activeFileName !== "all"
                contentItem: Text {
                    text: currentFileOnlyCheck.text
                    font.pixelSize: 12
                    color: currentFileOnlyCheck.enabled ? (t ? t.textPrimary : "#ffffff") : (t ? t.textMuted : "#666677")
                    leftPadding: currentFileOnlyCheck.indicator.width + 6
                    verticalAlignment: Text.AlignVCenter
                }
            }
        }

        Item { height: 6 }

        // Action Buttons
        RowLayout {
            Layout.fillWidth: true
            spacing: 12

            Item { Layout.fillWidth: true }

            Rectangle {
                width: 90; height: 34; radius: 8
                color: cancelMouse.containsMouse ? (t ? t.bgHover : "#32324a") : (t ? t.bg4 : "#2a2a3a")
                border.color: t ? t.border2 : "#3d3d55"
                border.width: 1
                Text {
                    anchors.centerIn: parent
                    text: localeManager.strings.common.cancel
                    color: t ? t.textPrimary : "#ffffff"
                    font.pixelSize: 12
                }
                MouseArea {
                    id: cancelMouse
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    hoverEnabled: true
                    onClicked: root.close()
                }
            }

            Rectangle {
                width: 130; height: 34; radius: 8
                color: replaceMouse.containsMouse ? (t ? t.accentDark : "#5a4dd4") : (t ? t.accent : "#7c6cf8")
                opacity: searchInput.text.length > 0 ? 1.0 : 0.5
                enabled: searchInput.text.length > 0

                Text {
                    anchors.centerIn: parent
                    text: localeManager.strings.batch_replace.replace_all_button
                    color: "#ffffff"
                    font.pixelSize: 12
                    font.bold: true
                }
                MouseArea {
                    id: replaceMouse
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    hoverEnabled: true
                    onClicked: {
                        if (searchInput.text.length > 0) {
                            var fileScope = currentFileOnlyCheck.checked ? root.activeFileName : "all"
                            root.replaceRequested(searchInput.text, replaceInput.text, fileScope, matchCaseCheck.checked)
                            root.close()
                        }
                    }
                }
            }
        }
    }

    function openWith(fileName) {
        root.activeFileName = fileName || "all"
        currentFileOnlyCheck.checked = (root.activeFileName !== "all")
        searchInput.text = ""
        replaceInput.text = ""
        root.open()
        searchInput.forceActiveFocus()
    }
}
