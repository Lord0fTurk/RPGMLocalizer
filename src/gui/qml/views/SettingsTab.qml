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

    // ---- Input Field ----
    component InputField: ColumnLayout {
        id: inputComp
        property string label: ""
        property string text: ""
        property string placeholder: ""
        property bool isPassword: false
        signal editingFinished(string newText)
        spacing: t ? t.spaceXS : 4
        Layout.fillWidth: true

        Text {
            text: inputComp.label
            font.pixelSize: 11
            font.bold: true
            color: t ? t.textSecondary : "#9090b8"
        }
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: 34
            radius: 8
            color: t ? t.bg4 : "#2a2a3a"
            border.color: txtInput.activeFocus ? (t ? t.accent : "#7c6cf8") : (t ? t.border2 : "#3d3d55")
            border.width: 1

            TextField {
                id: txtInput
                anchors.fill: parent
                anchors.leftMargin: 10
                anchors.rightMargin: 10
                text: inputComp.text
                placeholderText: inputComp.placeholder
                echoMode: inputComp.isPassword ? TextInput.Password : TextInput.Normal
                color: t ? t.textPrimary : "#f0f0ff"
                placeholderTextColor: t ? t.textMuted : "#55556a"
                font.pixelSize: t ? t.fontSizeSM : 12
                background: Item {}
                onEditingFinished: inputComp.editingFinished(text)
            }
        }
    }

    // ---- Styled Slider Row ----
    component StyledSlider: RowLayout {
        id: sliderRow
        property string label: ""
        property real from: 0; property real to: 100; property real step: 1
        property real value: 0
        signal moved(real val)
        spacing: 14; Layout.fillWidth: true

        Text {
            text: sliderRow.label + ": " + Math.round(sliderRow.value)
            font.pixelSize: t ? t.fontSizeSM : 12; color: t ? t.textSecondary : "#9090b8"
            Layout.preferredWidth: 210
        }
        Slider {
            Layout.fillWidth: true
            from: sliderRow.from; to: sliderRow.to; stepSize: sliderRow.step
            value: sliderRow.value
            Material.theme: Material.Dark; Material.accent: t ? t.accent : "#7c6cf8"
            onMoved: sliderRow.moved(value)
        }
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
            border.color: toggleRowComp.checked ? "transparent" : (t ? t.border2 : "#3d3d55")
            border.width: 1
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

    // =========================================================
    ScrollView {
        id: scrollView
        anchors.fill: parent
        contentWidth: availableWidth
        clip: true

        ColumnLayout {
            width: scrollView.availableWidth
            spacing: 0

            // Header
            Rectangle {
                Layout.fillWidth: true; implicitHeight: 68
                color: t ? t.bg2 : "#1a1a24"
                Rectangle { width: parent.width; height: 1; anchors.bottom: parent.bottom; color: t ? t.border1 : "#2e2e3e" }
                RowLayout {
                    anchors { fill: parent; leftMargin: 28 }
                    Text { text: "Settings"; font.pixelSize: 20; font.bold: true; color: t ? t.textPrimary : "#f0f0ff" }
                }
            }

            ColumnLayout {
                Layout.fillWidth: true; Layout.margins: 28; spacing: t ? t.spaceLG : 16

                // ===== CARD: Engine & Performance =====
                AppCard {
                    Layout.fillWidth: true
                    implicitHeight: engCardCol.implicitHeight + 40
                    ColumnLayout {
                        id: engCardCol
                        anchors { fill: parent; margins: 20 }
                        spacing: t ? t.spaceLG : 16
                        RowLayout {
                            spacing: t ? t.spaceSM : 8
                            Rectangle { width: 4; height: 16; radius: 2; color: t ? t.accent : "#7c6cf8" }
                            Text { text: "Engine & Performance"; font.pixelSize: 14; font.bold: true; color: t ? t.textPrimary : "#f0f0ff" }
                        }
                        Rectangle { Layout.fillWidth: true; height: 1; color: t ? t.border1 : "#2e2e3e" }
                        StyledSlider {
                            label: "Batch Size (Lines)"; from: 5; to: 50; step: 5
                            value: settingsBackend.batchSize
                            onMoved: (val) => { settingsBackend.batchSize = Math.round(val) }
                        }
                        StyledSlider {
                            label: "Concurrent Requests"; from: 1; to: 20; step: 1
                            value: settingsBackend.concurrentRequests
                            onMoved: (val) => { settingsBackend.concurrentRequests = Math.round(val) }
                        }
                        ToggleRow {
                            label: "Multi-Endpoint Racing"
                            desc: "Rotate Google mirror endpoints in parallel"
                            checked: settingsBackend.useMultiEndpoint
                            onToggled: (val) => { settingsBackend.useMultiEndpoint = val }
                        }
                        ToggleRow {
                            label: "Lingva Fallback"
                            desc: "Fall back to Lingva if Google fails"
                            checked: settingsBackend.enableLingvaFallback
                            onToggled: (val) => { settingsBackend.enableLingvaFallback = val }
                        }
                    }
                }

                // ===== CARD: AI & Provider Credentials =====
                AppCard {
                    Layout.fillWidth: true
                    implicitHeight: aiCardCol.implicitHeight + 40
                    ColumnLayout {
                        id: aiCardCol
                        anchors { fill: parent; margins: 20 }
                        spacing: t ? t.spaceLG : 16
                        RowLayout {
                            spacing: t ? t.spaceSM : 8
                            Rectangle { width: 4; height: 16; radius: 2; color: t ? t.accentLight : "#a89bf9" }
                            Text { text: "AI & External Provider Credentials"; font.pixelSize: 14; font.bold: true; color: t ? t.textPrimary : "#f0f0ff" }
                        }
                        Rectangle { Layout.fillWidth: true; height: 1; color: t ? t.border1 : "#2e2e3e" }

                        // OpenAI / DeepSeek
                        Text { text: "🤖 OpenAI / DeepSeek"; font.pixelSize: t ? t.fontSizeSM : 12; font.bold: true; color: t ? t.accentLight : "#a89bf9" }
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: t ? t.spaceMD : 12
                            InputField {
                                label: "API Key"
                                text: settingsBackend.openaiApiKey
                                placeholder: "sk-..."
                                isPassword: true
                                onEditingFinished: (newText) => { settingsBackend.openaiApiKey = newText }
                            }
                            InputField {
                                label: "Model Name"
                                text: settingsBackend.openaiModel
                                placeholder: "gpt-4o-mini"
                                onEditingFinished: (newText) => { settingsBackend.openaiModel = newText }
                            }
                        }
                        InputField {
                            label: "Base URL (Set to https://api.deepseek.com/v1 for DeepSeek)"
                            text: settingsBackend.openaiBaseUrl
                            placeholder: "https://api.openai.com/v1"
                            onEditingFinished: (newText) => { settingsBackend.openaiBaseUrl = newText }
                        }

                        Rectangle { Layout.fillWidth: true; height: 1; color: t ? t.border1 : "#2e2e3e" }

                        // Google Gemini
                        Text { text: "✨ Google Gemini"; font.pixelSize: t ? t.fontSizeSM : 12; font.bold: true; color: t ? t.accentLight : "#a89bf9" }
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: t ? t.spaceMD : 12
                            InputField {
                                label: "API Key"
                                text: settingsBackend.geminiApiKey
                                placeholder: "AIzaSy..."
                                isPassword: true
                                onEditingFinished: (newText) => { settingsBackend.geminiApiKey = newText }
                            }
                            InputField {
                                label: "Model Name"
                                text: settingsBackend.geminiModel
                                placeholder: "gemini-2.0-flash"
                                onEditingFinished: (newText) => { settingsBackend.geminiModel = newText }
                            }
                        }

                        Rectangle { Layout.fillWidth: true; height: 1; color: t ? t.border1 : "#2e2e3e" }

                        // Local LLM
                        Text { text: "🦙 Local LLM (Ollama / LM Studio)"; font.pixelSize: t ? t.fontSizeSM : 12; font.bold: true; color: t ? t.accentLight : "#a89bf9" }
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: t ? t.spaceMD : 12
                            InputField {
                                label: "Base URL"
                                text: settingsBackend.localLlmUrl
                                placeholder: "http://localhost:11434/v1"
                                onEditingFinished: (newText) => { settingsBackend.localLlmUrl = newText }
                            }
                            InputField {
                                label: "Model Name"
                                text: settingsBackend.localLlmModel
                                placeholder: "llama3"
                                onEditingFinished: (newText) => { settingsBackend.localLlmModel = newText }
                            }
                        }

                        Rectangle { Layout.fillWidth: true; height: 1; color: t ? t.border1 : "#2e2e3e" }

                        // DeepL & LibreTranslate
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: t ? t.spaceLG : 16
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: t ? t.spaceSM : 8
                                Text { text: "🎯 DeepL"; font.pixelSize: t ? t.fontSizeSM : 12; font.bold: true; color: t ? t.accentLight : "#a89bf9" }
                                InputField {
                                    label: "API Key"
                                    text: settingsBackend.deeplApiKey
                                    placeholder: "xxxxxxxx-xxxx-..."
                                    isPassword: true
                                    onEditingFinished: (newText) => { settingsBackend.deeplApiKey = newText }
                                }
                            }
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: t ? t.spaceSM : 8
                                Text { text: "🔓 LibreTranslate"; font.pixelSize: t ? t.fontSizeSM : 12; font.bold: true; color: t ? t.accentLight : "#a89bf9" }
                                InputField {
                                    label: "Server URL"
                                    text: settingsBackend.libretranslateUrl
                                    placeholder: "http://localhost:5000"
                                    onEditingFinished: (newText) => { settingsBackend.libretranslateUrl = newText }
                                }
                            }
                        }
                    }
                }

                // ===== CARD: Format & Protection =====
                AppCard {
                    Layout.fillWidth: true
                    implicitHeight: fmtCardCol.implicitHeight + 40
                    ColumnLayout {
                        id: fmtCardCol
                        anchors { fill: parent; margins: 20 }
                        spacing: t ? t.spaceLG : 16
                        RowLayout {
                            spacing: t ? t.spaceSM : 8
                            Rectangle { width: 4; height: 16; radius: 2; color: t ? t.success : "#4ade80" }
                            Text { text: "Formatting & Protection"; font.pixelSize: 14; font.bold: true; color: t ? t.textPrimary : "#f0f0ff" }
                        }
                        Rectangle { Layout.fillWidth: true; height: 1; color: t ? t.border1 : "#2e2e3e" }
                        ToggleRow {
                            label: "Auto Word-Wrap (<WordWrap>)"
                            desc: "Inject automatic line breaks in standard dialogue"
                            checked: settingsBackend.autoWordwrap
                            onToggled: (val) => { settingsBackend.autoWordwrap = val }
                        }
                        StyledSlider {
                            label: "Standard Dialogue Limit"; from: 25; to: 80; step: 1
                            value: settingsBackend.wordwrapLimitStandard
                            onMoved: (val) => { settingsBackend.wordwrapLimitStandard = Math.round(val) }
                        }
                        ToggleRow {
                            label: "Translate Editor Notes"
                            desc: "Include note tags and plugin parameters"
                            checked: settingsBackend.translateNotes
                            onToggled: (val) => { settingsBackend.translateNotes = val }
                        }
                        ToggleRow {
                            label: "Plugin JS UI Labels"
                            desc: "Extract translatable strings from plugins.js"
                            checked: settingsBackend.pluginJsUiExtraction
                            onToggled: (val) => { settingsBackend.pluginJsUiExtraction = val }
                        }
                    }
                }

                // ===== CARD: Safety & Cache =====
                AppCard {
                    Layout.fillWidth: true
                    implicitHeight: safeCardCol.implicitHeight + 40
                    ColumnLayout {
                        id: safeCardCol
                        anchors { fill: parent; margins: 20 }
                        spacing: t ? t.spaceLG : 16
                        RowLayout {
                            spacing: t ? t.spaceSM : 8
                            Rectangle { width: 4; height: 16; radius: 2; color: t ? t.warning : "#facc15" }
                            Text { text: "Safety & Cache"; font.pixelSize: 14; font.bold: true; color: t ? t.textPrimary : "#f0f0ff" }
                        }
                        Rectangle { Layout.fillWidth: true; height: 1; color: t ? t.border1 : "#2e2e3e" }
                        ToggleRow {
                            label: "Backup Game Data"
                            desc: "Copy original files to _backup/ before translation"
                            checked: settingsBackend.backupEnabled
                            onToggled: (val) => { settingsBackend.backupEnabled = val }
                        }
                        ToggleRow {
                            label: "Persistent Translation Cache"
                            desc: "Skip re-translating previously translated strings"
                            checked: settingsBackend.useCache
                            onToggled: (val) => { settingsBackend.useCache = val }
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            Item { Layout.fillWidth: true }
                            Rectangle {
                                implicitWidth: 160; implicitHeight: 34; radius: 8
                                color: clearMouse.pressed ? Qt.rgba(248, 113, 113, 0.25) : (clearMouse.containsMouse ? Qt.rgba(248, 113, 113, 0.15) : Qt.rgba(248, 113, 113, 0.08))
                                border.color: Qt.rgba(248, 113, 113, 0.4); border.width: 1
                                Behavior on color { ColorAnimation { duration: 130 } }
                                Text { anchors.centerIn: parent; text: "🗑  Clear Cache"; font.pixelSize: t ? t.fontSizeSM : 12; color: t ? t.danger : "#f87171" }
                                MouseArea {
                                    id: clearMouse; anchors.fill: parent; hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor; onClicked: appBackend.clearCache()
                                }
                            }
                        }
                    }
                }

                Item { height: 20 }
            }
        }
    }
}
