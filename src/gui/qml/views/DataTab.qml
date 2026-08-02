import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Controls.Material 2.15
import QtQuick.Layouts 1.15

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
            Layout.fillWidth: true; spacing: 1
            Text { text: toggleRowComp.label; font.pixelSize: t ? t.fontSizeMD : 13; color: t ? t.textPrimary : "#f0f0ff" }
            Text { text: toggleRowComp.desc; font.pixelSize: 11; color: t ? t.textMuted : "#55556a"; visible: text.length > 0 }
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
                        Text { text: "Data Tools"; font.pixelSize: 20; font.bold: true; color: t ? t.textPrimary : "#f0f0ff" }
                        Text { text: "Export, import and manage translation sidecars"; font.pixelSize: t ? t.fontSizeSM : 12; color: t ? t.textMuted : "#55556a" }
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
                            Text { text: "Export Sidecar"; font.pixelSize: 14; font.bold: true; color: t ? t.textPrimary : "#f0f0ff" }
                            Item { Layout.fillWidth: true }
                            // Format badge
                            Rectangle {
                                implicitHeight: 20; radius: t ? t.radiusMD : 10; implicitWidth: fmtTxt.implicitWidth + 14
                                color: Qt.rgba(124, 108, 248, 0.12); border.color: Qt.rgba(124, 108, 248, 0.3); border.width: 1
                                Text { id: fmtTxt; anchors.centerIn: parent; text: "CSV · JSON · PO"; font.pixelSize: 9; color: t ? t.accentLight : "#a89bf9" }
                            }
                        }
                        Rectangle { Layout.fillWidth: true; height: 1; color: t ? t.border1 : "#2e2e3e" }

                        FilePicker {
                            placeholder: "Select output file path..."
                            value: settingsBackend.exportPath
                            buttonLabel: "Save As..."
                            onBrowse: {
                                var p = appBackend.selectExportFile()
                                if (p) settingsBackend.exportPath = p
                            }
                        }

                        ToggleRow {
                            label: "Export Only Mode"
                            desc: "Do not write translations back to game data files"
                            checked: settingsBackend.exportOnly
                            onToggled: settingsBackend.exportOnly = val
                        }
                        ToggleRow {
                            label: "Distinct Entries Only"
                            desc: "Group identical source strings to reduce file size"
                            checked: settingsBackend.exportDistinct
                            onToggled: settingsBackend.exportDistinct = val
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
                            Text { text: "Import Sidecar"; font.pixelSize: 14; font.bold: true; color: t ? t.textPrimary : "#f0f0ff" }
                            Item { Layout.fillWidth: true }
                            Rectangle {
                                implicitHeight: 20; radius: t ? t.radiusMD : 10; implicitWidth: impFmtTxt.implicitWidth + 14
                                color: Qt.rgba(74, 222, 128, 0.10); border.color: Qt.rgba(74, 222, 128, 0.25); border.width: 1
                                Text { id: impFmtTxt; anchors.centerIn: parent; text: "CSV · JSON · PO"; font.pixelSize: 9; color: t ? t.success : "#4ade80" }
                            }
                        }
                        Rectangle { Layout.fillWidth: true; height: 1; color: t ? t.border1 : "#2e2e3e" }

                        Text {
                            text: "Apply a previously exported sidecar file to inject translations directly into the game data."
                            font.pixelSize: t ? t.fontSizeSM : 12; color: t ? t.textMuted : "#55556a"
                            wrapMode: Text.Wrap; Layout.fillWidth: true
                        }

                        FilePicker {
                            placeholder: "Select translated sidecar file..."
                            value: settingsBackend.importPath
                            buttonLabel: "Browse..."
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
                            Text { text: "Glossary Dictionary"; font.pixelSize: 14; font.bold: true; color: t ? t.textPrimary : "#f0f0ff" }
                            Item { Layout.fillWidth: true }
                            Rectangle {
                                implicitHeight: 20; radius: t ? t.radiusMD : 10; implicitWidth: glossFmtTxt.implicitWidth + 14
                                color: Qt.rgba(250, 204, 21, 0.08); border.color: Qt.rgba(250, 204, 21, 0.25); border.width: 1
                                Text { id: glossFmtTxt; anchors.centerIn: parent; text: "JSON · CSV"; font.pixelSize: 9; color: t ? t.warning : "#facc15" }
                            }
                        }
                        Rectangle { Layout.fillWidth: true; height: 1; color: t ? t.border1 : "#2e2e3e" }

                        Text {
                            text: "Define term mappings that override automatic translation for specific words (e.g. character names, skill names)."
                            font.pixelSize: t ? t.fontSizeSM : 12; color: t ? t.textMuted : "#55556a"
                            wrapMode: Text.Wrap; Layout.fillWidth: true
                        }

                        ToggleRow {
                            label: "Use Custom Glossary"
                            desc: "Apply the selected dictionary during translation"
                            checked: settingsBackend.useGlossary
                            onToggled: settingsBackend.useGlossary = val
                        }

                        FilePicker {
                            placeholder: "Select glossary JSON/CSV file..."
                            value: settingsBackend.glossaryPath
                            buttonLabel: "Browse..."
                            onBrowse: appBackend.selectGlossaryFile()
                        }
                    }
                }

                Item { height: 20 }
            }
        }
    }
}
