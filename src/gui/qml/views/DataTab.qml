import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Controls.Material 2.15
import QtQuick.Layouts 1.15
import "../js/I18n.js" as I18n

Item {
    id: root
    property var themeObj: null
    property var t: themeObj

    // ---- Reusable Card ----
    component AppCard: Rectangle {
        color: t ? t.bg3 : "#22222f"
        border.color: t ? t.border1 : "#2e2e3e"
        border.width: 1; radius: 12
    }

    // ---- Toggle Row ----
    component ToggleRow: RowLayout {
        id: toggleRowComp
        property string label: ""
        property string desc: ""
        property bool checked: false
        signal toggled(bool val)
        spacing: t ? t.spaceMD : 12; Layout.fillWidth: true
        ColumnLayout {
            Layout.fillWidth: true; spacing: 2
            Text { text: toggleRowComp.label; font.pixelSize: t ? t.fontSizeMD : 13; color: t ? t.textPrimary : "#f0f0ff" }
            Text { text: toggleRowComp.desc; font.pixelSize: 11; color: t ? t.textSecondary : "#9090b8"; opacity: 0.85; visible: text.length > 0 }
        }
        Rectangle {
            width: 42; height: 24; radius: 12
            color: toggleRowComp.checked ? (t ? t.accent : "#7c6cf8") : (t ? t.bg4 : "#2a2a3a")
            border.color: toggleRowComp.checked ? "transparent" : (t ? t.border2 : "#3d3d55"); border.width: 1
            Behavior on color { ColorAnimation { duration: t ? t.animFast : 130 } }
            Rectangle {
                width: 18; height: 18; radius: 9; anchors.verticalCenter: parent.verticalCenter
                x: toggleRowComp.checked ? parent.width - width - 3 : 3
                color: toggleRowComp.checked ? "white" : (t ? t.textMuted : "#55556a")
                Behavior on x     { NumberAnimation { duration: t ? t.animFast : 130; easing.type: Easing.OutQuad } }
                Behavior on color { ColorAnimation   { duration: t ? t.animFast : 130 } }
            }
            MouseArea {
                anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                onClicked: { toggleRowComp.checked = !toggleRowComp.checked; toggleRowComp.toggled(toggleRowComp.checked) }
            }
        }
    }

    // ---- File Picker Row ----
    component FilePicker: RowLayout {
        id: fpRow
        property string placeholder: "Select a file..."
        property string value: ""
        property string buttonLabel: "Browse..."
        signal browse()
        spacing: 10; Layout.fillWidth: true

        Rectangle {
            Layout.fillWidth: true; height: 36; radius: 8
            color: t ? t.bg4 : "#2a2a3a"
            border.color: t ? t.border2 : "#3d3d55"; border.width: 1
            RowLayout {
                anchors { fill: parent; leftMargin: 12; rightMargin: 8 }
                spacing: 8
                Text {
                    id: fpIcon
                    text: fpRow.value ? "📄" : "📁"
                    font.pixelSize: t ? t.fontSizeMD : 13; Layout.alignment: Qt.AlignVCenter
                }
                Text {
                    text: fpRow.value ? fpRow.value.split(/[/\\]/).pop() : fpRow.placeholder
                    font.pixelSize: t ? t.fontSizeSM : 12
                    color: fpRow.value ? (t ? t.textPrimary : "#f0f0ff") : (t ? t.textMuted : "#55556a")
                    elide: Text.ElideLeft; Layout.fillWidth: true
                }
            }
        }
        Rectangle {
            implicitWidth: browseText.implicitWidth + 24; implicitHeight: 36; radius: 8
            color: browseMouse.pressed ? (t ? t.bg4 : "#2a2a3a") : (browseMouse.containsMouse ? (t ? t.bgHover : "#32324a") : "transparent")
            border.color: t ? t.border2 : "#3d3d55"; border.width: 1
            Behavior on color { ColorAnimation { duration: 120 } }
            Text { id: browseText; anchors.centerIn: parent; text: fpRow.buttonLabel; font.pixelSize: t ? t.fontSizeSM : 12; color: t ? t.textSecondary : "#9090b8" }
            MouseArea {
                id: browseMouse; anchors.fill: parent; hoverEnabled: true
                cursorShape: Qt.PointingHandCursor; onClicked: fpRow.browse()
            }
        }
    }

    // =========================================================
    ScrollView {
        id: scrollView
        anchors.fill: parent; contentWidth: availableWidth; clip: true

        ColumnLayout {
            width: scrollView.availableWidth; spacing: 0

            // Header
            Rectangle {
                Layout.fillWidth: true; implicitHeight: 68
                color: t ? t.bg2 : "#1a1a24"
                Rectangle { width: parent.width; height: 1; anchors.bottom: parent.bottom; color: t ? t.border1 : "#2e2e3e" }
                RowLayout {
                    anchors { fill: parent; leftMargin: 28; rightMargin: 28 }
                    ColumnLayout {
                        spacing: 2
                        Text { text: localeManager.strings.data.header_title; font.pixelSize: 20; font.bold: true; color: t ? t.textPrimary : "#f0f0ff" }
                        Text { text: localeManager.strings.data.header_subtitle; font.pixelSize: t ? t.fontSizeSM : 12; color: t ? t.textMuted : "#55556a" }
                    }
                    Item { Layout.fillWidth: true }
                    // Telemetry Pill Badge
                    Rectangle {
                        implicitHeight: 28
                        implicitWidth: teleTxt.implicitWidth + 24
                        radius: 14
                        color: appBackend.projectPath ? Qt.rgba(124, 108, 248, 0.12) : Qt.rgba(255, 255, 255, 0.05)
                        border.color: appBackend.projectPath ? Qt.rgba(124, 108, 248, 0.3) : (t ? t.border1 : "#2e2e3e")
                        border.width: 1

                        RowLayout {
                            anchors.centerIn: parent
                            spacing: 8
                            Rectangle {
                                width: 7; height: 7; radius: 3.5
                                color: appBackend.projectPath ? (t ? t.accentLight : "#a89bf9") : (t ? t.textMuted : "#55556a")
                            }
                            Text {
                                id: teleTxt
                                text: appBackend.projectPath ?
                                      (editorBackend.totalProjectCount > 0 ?
                                       I18n.format(localeManager.strings.data.telemetry_loaded, {count: editorBackend.totalProjectCount}) :
                                       (appBackend.detectedEngine.length > 0 ? ("🎮 " + appBackend.detectedEngine) : "📁 " + (appBackend.projectPath.split(/[/\\]/).pop() || ""))) :
                                      localeManager.strings.data.telemetry_none
                                font.pixelSize: t ? t.fontSizeSM : 12
                                color: appBackend.projectPath ? (t ? t.textPrimary : "#f0f0ff") : (t ? t.textMuted : "#55556a")
                            }
                        }
                    }
                }
            }

            ColumnLayout {
                Layout.fillWidth: true; Layout.margins: 28; spacing: t ? t.spaceLG : 16

                // ===== CARD: Export Sidecar =====
                AppCard {
                    Layout.fillWidth: true
                    implicitHeight: exportCol.implicitHeight + 40
                    ColumnLayout {
                        id: exportCol; anchors { fill: parent; margins: 20 }
                        spacing: 14
                        RowLayout {
                            spacing: t ? t.spaceSM : 8
                            Rectangle { width: 4; height: 16; radius: 2; color: t ? t.accent : "#7c6cf8" }
                            Text { text: localeManager.strings.data.export_card_title; font.pixelSize: 14; font.bold: true; color: t ? t.textPrimary : "#f0f0ff" }
                            Item { Layout.fillWidth: true }
                            // Format badge
                            Rectangle {
                                implicitHeight: 20; radius: t ? t.radiusMD : 10; implicitWidth: fmtTxt.implicitWidth + 14
                                color: Qt.rgba(124, 108, 248, 0.12); border.color: Qt.rgba(124, 108, 248, 0.3); border.width: 1
                                Text { id: fmtTxt; anchors.centerIn: parent; text: localeManager.strings.data.format_csv_json_po; font.pixelSize: 9; color: t ? t.accentLight : "#a89bf9" }
                            }
                        }
                        Rectangle { Layout.fillWidth: true; height: 1; color: t ? t.border1 : "#2e2e3e" }

                        FilePicker {
                            placeholder: localeManager.strings.data.export_path_placeholder
                            value: settingsBackend.exportPath
                            buttonLabel: localeManager.strings.data.save_as_button
                            onBrowse: {
                                var p = appBackend.selectExportFile()
                                if (p) settingsBackend.exportPath = p
                            }
                        }

                        ToggleRow {
                            label: localeManager.strings.data.export_only_label
                            desc: localeManager.strings.data.export_only_desc
                            checked: settingsBackend.exportOnly
                            onToggled: (val) => { settingsBackend.exportOnly = val }
                        }
                        ToggleRow {
                            label: localeManager.strings.data.export_distinct_label
                            desc: localeManager.strings.data.export_distinct_desc
                            checked: settingsBackend.exportDistinct
                            onToggled: (val) => { settingsBackend.exportDistinct = val }
                        }
                    }
                }

                // ===== CARD: Import Sidecar =====
                AppCard {
                    Layout.fillWidth: true
                    implicitHeight: importCol.implicitHeight + 40
                    ColumnLayout {
                        id: importCol; anchors { fill: parent; margins: 20 }
                        spacing: 14
                        RowLayout {
                            spacing: t ? t.spaceSM : 8
                            Rectangle { width: 4; height: 16; radius: 2; color: t ? t.success : "#4ade80" }
                            Text { text: localeManager.strings.data.import_card_title; font.pixelSize: 14; font.bold: true; color: t ? t.textPrimary : "#f0f0ff" }
                            Item { Layout.fillWidth: true }
                            Rectangle {
                                implicitHeight: 20; radius: t ? t.radiusMD : 10; implicitWidth: impFmtTxt.implicitWidth + 14
                                color: Qt.rgba(74, 222, 128, 0.10); border.color: Qt.rgba(74, 222, 128, 0.25); border.width: 1
                                Text { id: impFmtTxt; anchors.centerIn: parent; text: localeManager.strings.data.format_csv_json_po; font.pixelSize: 9; color: t ? t.success : "#4ade80" }
                            }
                        }
                        Rectangle { Layout.fillWidth: true; height: 1; color: t ? t.border1 : "#2e2e3e" }

                        Text {
                            text: localeManager.strings.data.import_desc
                            font.pixelSize: t ? t.fontSizeSM : 12; color: t ? t.textMuted : "#55556a"
                            wrapMode: Text.Wrap; Layout.fillWidth: true
                        }

                        FilePicker {
                            placeholder: localeManager.strings.data.import_path_placeholder
                            value: settingsBackend.importPath
                            buttonLabel: localeManager.strings.data.browse_button
                            onBrowse: {
                                var p = appBackend.selectImportFile()
                                if (p) settingsBackend.importPath = p
                            }
                        }
                    }
                }

                // ===== CARD: Glossary Manager =====
                AppCard {
                    Layout.fillWidth: true
                    implicitHeight: glossaryCol.implicitHeight + 40
                    ColumnLayout {
                        id: glossaryCol; anchors { fill: parent; margins: 20 }
                        spacing: 14
                        RowLayout {
                            spacing: t ? t.spaceSM : 8
                            Rectangle { width: 4; height: 16; radius: 2; color: t ? t.warning : "#facc15" }
                            Text { text: localeManager.strings.data.glossary_card_title; font.pixelSize: 14; font.bold: true; color: t ? t.textPrimary : "#f0f0ff" }
                            Item { Layout.fillWidth: true }
                            Rectangle {
                                implicitHeight: 20; radius: t ? t.radiusMD : 10; implicitWidth: glossFmtTxt.implicitWidth + 14
                                color: Qt.rgba(250, 204, 21, 0.08); border.color: Qt.rgba(250, 204, 21, 0.25); border.width: 1
                                Text { id: glossFmtTxt; anchors.centerIn: parent; text: localeManager.strings.data.glossary_format_badge; font.pixelSize: 9; color: t ? t.warning : "#facc15" }
                            }
                        }
                        Rectangle { Layout.fillWidth: true; height: 1; color: t ? t.border1 : "#2e2e3e" }

                        Text {
                            text: localeManager.strings.data.glossary_desc
                            font.pixelSize: t ? t.fontSizeSM : 12; color: t ? t.textMuted : "#55556a"
                            wrapMode: Text.Wrap; Layout.fillWidth: true
                        }

                        ToggleRow {
                            label: localeManager.strings.data.use_glossary_label
                            desc: localeManager.strings.data.use_glossary_desc
                            checked: settingsBackend.useGlossary
                            onToggled: (val) => { settingsBackend.useGlossary = val }
                        }

                        FilePicker {
                            placeholder: localeManager.strings.data.glossary_path_placeholder
                            value: settingsBackend.glossaryPath
                            buttonLabel: localeManager.strings.data.browse_button
                            onBrowse: appBackend.selectGlossaryFile()
                        }
                    }
                }

                Item { height: 20 }
            }
        }
    }
}
