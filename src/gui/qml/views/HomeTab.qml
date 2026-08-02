import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Controls.Material 2.15
import QtQuick.Layouts 1.15

Item {
    id: root
    property var themeObj: null
    property var t: themeObj

    // =========================================================
    // REUSABLE COMPONENTS
    // =========================================================
    component AppCard: Rectangle {
        color: t ? t.bg3 : "#22222f"
        border.color: t ? t.border1 : "#2e2e3e"
        border.width: 1
        radius: 12
    }

    component SectionLabel: Text {
        font.pixelSize: t ? t.fontSizeXS : 10
        font.bold: true
        font.letterSpacing: 1.0
        color: t ? t.textMuted : "#55556a"
    }

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

    component AccentButton: Rectangle {
        id: accentBtn
        property string label: "Button"
        property bool enabled_: true
        signal clicked()
        implicitHeight: 38
        radius: 9
        opacity: enabled_ ? 1.0 : 0.4
        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0.0; color: t ? t.accentDark : "#5a4dd4" }
            GradientStop { position: 1.0; color: t ? t.accent    : "#7c6cf8" }
        }
        Behavior on opacity { NumberAnimation { duration: t ? t.animFast : 130 } }
        Rectangle {
            anchors.fill: parent; radius: parent.radius
            color: abMouse.containsMouse ? Qt.rgba(255,255,255,0.08) : "transparent"
            Behavior on color { ColorAnimation { duration: t ? t.animFast : 130 } }
        }
        Text {
            anchors.centerIn: parent; text: accentBtn.label
            color: "white"; font.pixelSize: t ? t.fontSizeMD : 13; font.bold: true
        }
        MouseArea {
            id: abMouse; anchors.fill: parent; hoverEnabled: true
            cursorShape: enabled_ ? Qt.PointingHandCursor : Qt.ArrowCursor
            enabled: accentBtn.enabled_
            onClicked: accentBtn.clicked()
        }
    }

    component GhostButton: Rectangle {
        id: ghostBtn
        property string label: "Button"
        signal clicked()
        implicitHeight: 36; radius: 9
        color: gbMouse.pressed ? (t ? t.bg4 : "#2a2a3a") : (gbMouse.containsMouse ? (t ? t.bgHover : "#32324a") : "transparent")
        border.color: t ? t.border2 : "#3d3d55"; border.width: 1
        Behavior on color { ColorAnimation { duration: t ? t.animFast : 130 } }
        Text { anchors.centerIn: parent; text: ghostBtn.label; color: t ? t.textSecondary : "#9090b8"; font.pixelSize: t ? t.fontSizeMD : 13 }
        MouseArea {
            id: gbMouse; anchors.fill: parent; hoverEnabled: true
            cursorShape: Qt.PointingHandCursor; onClicked: ghostBtn.clicked()
        }
    }

    component StyledCombo: ComboBox {
        id: styledCombo
        Material.theme: Material.Dark
        implicitHeight: 36
        background: Rectangle {
            color: styledCombo.popup.visible ? (t ? t.bg4 : "#2a2a3a") : (styledCombo.hovered ? (t ? t.bgHover : "#32324a") : (t ? t.bg4 : "#22222f"))
            border.color: styledCombo.popup.visible ? (t ? t.accent : "#7c6cf8") : (t ? t.border2 : "#3d3d55")
            border.width: 1; radius: 8
            Behavior on color { ColorAnimation { duration: t ? t.animFast : 130 } }
            Behavior on border.color { ColorAnimation { duration: t ? t.animFast : 130 } }
        }
        contentItem: Text {
            leftPadding: 12; rightPadding: styledCombo.indicator.width + 8
            text: styledCombo.displayText; color: t ? t.textPrimary : "#f0f0ff"
            font.pixelSize: t ? t.fontSizeMD : 13; verticalAlignment: Text.AlignVCenter
        }
        indicator: Text {
            x: styledCombo.width - width - 10; y: (styledCombo.height - height) / 2
            text: "▾"; color: t ? t.textSecondary : "#9090b8"; font.pixelSize: 11
            rotation: styledCombo.popup.visible ? 180 : 0
            Behavior on rotation { NumberAnimation { duration: 150 } }
        }
        popup: Popup {
            y: styledCombo.height + 4; width: styledCombo.width
            implicitHeight: contentItem.implicitHeight; padding: 4
            background: Rectangle {
                color: t ? t.bg3 : "#22222f"; border.color: t ? t.border2 : "#3d3d55"
                border.width: 1; radius: t ? t.radiusMD : 10
            }
            contentItem: ListView {
                clip: true; implicitHeight: Math.min(contentHeight, 280)
                model: styledCombo.delegateModel
                ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
            }
        }
        delegate: ItemDelegate {
            width: styledCombo.width - 8
            highlighted: styledCombo.highlightedIndex === index
            contentItem: Text {
                text: modelData; font.pixelSize: t ? t.fontSizeMD : 13; leftPadding: 8
                color: highlighted ? "white" : (t ? t.textSecondary : "#9090b8")
                verticalAlignment: Text.AlignVCenter
            }
            background: Rectangle {
                color: highlighted ? (t ? t.accentGlow : "#1c1c30") : "transparent"; radius: t ? t.radiusSM : 6
            }
        }
    }

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
            Text { text: toggleRowComp.desc; font.pixelSize: 11; color: t ? t.textMuted : "#55556a"; visible: text.length > 0; wrapMode: Text.WordWrap; Layout.fillWidth: true }
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

    // =========================================================
    // HOME TAB
    // =========================================================
    ScrollView {
        id: scrollView
        anchors.fill: parent
        contentWidth: availableWidth
        clip: true

        ColumnLayout {
            width: scrollView.availableWidth
            spacing: 0

            // --- Header ---
            Rectangle {
                Layout.fillWidth: true; implicitHeight: 68
                color: t ? t.bg2 : "#1a1a24"
                Rectangle { width: parent.width; height: 1; anchors.bottom: parent.bottom; color: t ? t.border1 : "#2e2e3e" }
                RowLayout {
                    anchors { fill: parent; leftMargin: 28; rightMargin: 28 }
                    spacing: t ? t.spaceMD : 12
                    ColumnLayout {
                        spacing: 2
                        Text { text: "RPG Maker Localizer"; font.pixelSize: 20; font.bold: true; color: t ? t.textPrimary : "#f0f0ff" }
                        Text { text: "Ruby RGSS 1/2/3  ·  MV / MZ JS  ·  Autonomous translation engine"; font.pixelSize: t ? t.fontSizeSM : 12; color: t ? t.textMuted : "#55556a" }
                    }
                    Item { Layout.fillWidth: true }
                    Rectangle {
                        visible: appBackend.isRunning
                        implicitWidth: 110; implicitHeight: 28; radius: t ? t.radiusLG : 14
                        color: Qt.rgba(74, 222, 128, 0.12)
                        border.color: Qt.rgba(74, 222, 128, 0.35); border.width: 1
                        RowLayout {
                            anchors.centerIn: parent; spacing: 6
                            Rectangle {
                                width: 7; height: 7; radius: 3.5; color: t ? t.success : "#4ade80"
                                SequentialAnimation on opacity {
                                    loops: Animation.Infinite
                                    NumberAnimation { to: 0.2; duration: 800 }
                                    NumberAnimation { to: 1.0; duration: 800 }
                                }
                            }
                            Text { text: "Translating"; color: t ? t.success : "#4ade80"; font.pixelSize: t ? t.fontSizeSM : 12 }
                        }
                    }
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                Layout.margins: 28
                spacing: 18

                // --- DROP ZONE ---
                AppCard {
                    id: dropCard
                    Layout.fillWidth: true; implicitHeight: 120
                    property bool dropActive: false

                    Rectangle {
                        anchors.fill: parent; radius: parent.radius
                        color: dropCard.dropActive ? Qt.rgba(124, 108, 248, 0.08) : "transparent"
                        border.color: dropCard.dropActive ? (t ? t.accent : "#7c6cf8") : "transparent"
                        border.width: dropCard.dropActive ? 2 : 0
                        Behavior on color { ColorAnimation { duration: t ? t.animFast : 130 } }
                    }
                    DropArea {
                        anchors.fill: parent
                        onEntered: dropCard.dropActive = true
                        onExited:  dropCard.dropActive = false
                        onDropped: {
                            dropCard.dropActive = false
                            if (drop.hasUrls) {
                                // QUrl.fromLocalFile round-trip correctly decodes percent-encoded
                                // file:/// URLs (e.g. spaces as %20) on Windows and Linux/macOS
                                var rawUrl = drop.urls[0].toString()
                                // On Windows: "file:///C:/..." → "C:/..."
                                // On Linux/macOS: "file:///home/..." → "/home/..."
                                var localPath = rawUrl.replace(/^file:\/\/\//, "").replace(/^file:\/\//, "/")
                                // Decode percent-encoding (%20 → space, etc.)
                                localPath = decodeURIComponent(localPath)
                                appBackend.setProjectPath(localPath)
                            }
                        }
                    }
                    RowLayout {
                        anchors { fill: parent; margins: 24 }
                        spacing: 20
                        Rectangle {
                            width: 52; height: 52; radius: 12
                            color: appBackend.projectPath ? Qt.rgba(124, 108, 248, 0.15) : Qt.rgba(255,255,255,0.04)
                            border.color: appBackend.projectPath ? Qt.rgba(124, 108, 248, 0.35) : (t ? t.border1 : "#2e2e3e")
                            border.width: 1
                            Behavior on color { ColorAnimation { duration: t ? t.animMedium : 220 } }
                            Text { anchors.centerIn: parent; text: appBackend.projectPath ? "✅" : "📂"; font.pixelSize: 22 }
                        }
                        ColumnLayout {
                            Layout.fillWidth: true; spacing: t ? t.spaceXS : 4
                            Text {
                                text: appBackend.projectPath ? appBackend.projectPath.split(/[/\\]/).pop() : "Drag Game Folder or Browse"
                                font.pixelSize: t ? t.fontSizeLG : 15; font.bold: true; color: t ? t.textPrimary : "#f0f0ff"
                                elide: Text.ElideMiddle; Layout.fillWidth: true
                            }
                            Text {
                                text: appBackend.projectPath ? appBackend.projectPath : "RPG Maker project directory containing Data/ or js/ folder"
                                font.pixelSize: t ? t.fontSizeSM : 12; color: t ? t.textMuted : "#55556a"
                                elide: Text.ElideMiddle; Layout.fillWidth: true
                            }
                        }
                        GhostButton {
                            label: "  Browse...  "; implicitWidth: 90
                            onClicked: appBackend.selectProjectDirectory()
                        }
                    }
                }

                // --- LANGUAGE & ENGINE CARD ---
                AppCard {
                    id: langCard
                    Layout.fillWidth: true
                    implicitHeight: langCardCol.implicitHeight + 36

                    // Full language list: display name → language code
                    property var langNames: [
                        "Auto Detect","Afrikaans","Albanian","Amharic","Arabic","Armenian","Assamese",
                        "Aymara","Azerbaijani","Bambara","Basque","Belarusian","Bengali","Bhojpuri",
                        "Bosnian","Bulgarian","Catalan","Cebuano","Chinese (Simplified)","Chinese (Traditional)",
                        "Corsican","Croatian","Czech","Danish","Dhivehi","Dogri","Dutch","English",
                        "Esperanto","Estonian","Ewe","Filipino","Finnish","French","Frisian","Galician",
                        "Georgian","German","Greek","Guarani","Gujarati","Haitian Creole","Hausa",
                        "Hawaiian","Hebrew","Hindi","Hmong","Hungarian","Icelandic","Igbo","Ilocano",
                        "Indonesian","Irish","Italian","Japanese","Javanese","Kannada","Kazakh","Khmer",
                        "Kinyarwanda","Konkani","Korean","Krio","Kurdish","Kurdish (Sorani)","Kyrgyz",
                        "Lao","Latin","Latvian","Lingala","Lithuanian","Luganda","Luxembourgish",
                        "Macedonian","Maithili","Malagasy","Malay","Malayalam","Maltese","Maori",
                        "Marathi","Meiteilon (Manipuri)","Mizo","Mongolian","Myanmar (Burmese)","Nepali",
                        "Norwegian","Nyanja (Chichewa)","Odia (Oriya)","Oromo","Pashto","Persian",
                        "Polish","Portuguese","Portuguese (Brazil)","Punjabi","Quechua","Romanian",
                        "Russian","Samoan","Sanskrit","Scots Gaelic","Serbian","Sesotho","Shona",
                        "Sindhi","Sinhala","Slovak","Slovenian","Somali","Spanish","Sundanese","Swahili",
                        "Swedish","Tajik","Tamil","Tatar","Telugu","Thai","Tigrinya","Tsonga","Turkish",
                        "Turkmen","Twi (Akan)","Ukrainian","Urdu","Uyghur","Uzbek","Vietnamese","Welsh",
                        "Xhosa","Yiddish","Yoruba","Zulu"
                    ]
                    property var langCodes: [
                        "auto","af","sq","am","ar","hy","as","ay","az","bm","eu","be","bn","bho",
                        "bs","bg","ca","ceb","zh-CN","zh-TW","co","hr","cs","da","dv","doi","nl","en",
                        "eo","et","ee","tl","fi","fr","fy","gl","ka","de","el","gn","gu","ht","ha",
                        "haw","he","hi","hmn","hu","is","ig","ilo","id","ga","it","ja","jv","kn","kk",
                        "km","rw","gom","ko","kri","ku","ckb","ky","lo","la","lv","ln","lt","lg","lb",
                        "mk","mai","mg","ms","ml","mt","mi","mr","mni","lus","mn","my","ne","no","ny",
                        "or","om","ps","fa","pl","pt","pt-BR","pa","qu","ro","ru","sm","sa","gd","sr",
                        "st","sn","sd","si","sk","sl","so","es","su","sw","sv","tg","ta","tt","te",
                        "th","ti","ts","tr","tk","ak","uk","ur","ug","uz","vi","cy","xh","yi","yo","zu"
                    ]
                    property var targetLangNames: langNames.slice(1)
                    property var targetLangCodes: langCodes.slice(1)

                    // Engine info: id, display name, icon, description
                    property var engineDefs: [
                        { id: "google",         name: "Google Translate",   icon: "🌐", desc: "Free · 130+ languages · Multi-endpoint racing" },
                        { id: "lingva",         name: "Lingva",             icon: "🔄", desc: "Free · Privacy-friendly Google frontend" },
                        { id: "deepl",          name: "DeepL",              icon: "🎯", desc: "High quality · API key required" },
                        { id: "openai",         name: "OpenAI / ChatGPT",   icon: "🤖", desc: "AI-powered · Context-aware · API key required" },
                        { id: "gemini",         name: "Google Gemini",      icon: "✨", desc: "AI-powered · Gemini Pro · API key required" },
                        { id: "local_llm",      name: "Local LLM (Ollama)", icon: "🦙", desc: "Offline · Custom models · No API key" },
                        { id: "libretranslate", name: "LibreTranslate",     icon: "🔓", desc: "Open-source · Self-hostable · Optional API key" },
                    ]
                    property var engineIds: engineDefs.map(function(e) { return e.id })
                    property var engineNames: engineDefs.map(function(e) { return e.name })

                    function codeToIndex(codes, code) {
                        for (var i = 0; i < codes.length; i++)
                            if (codes[i] === code) return i
                        return 0
                    }
                    function engineIdToIndex(id) {
                        for (var i = 0; i < engineIds.length; i++)
                            if (engineIds[i] === id) return i
                        return 0
                    }

                    ColumnLayout {
                        id: langCardCol
                        anchors { fill: parent; margins: 18 }
                        spacing: t ? t.spaceLG : 16

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: t ? t.spaceMD : 12

                            // Engine selector
                            ColumnLayout {
                                spacing: 5
                                Layout.preferredWidth: 200
                                SectionLabel { text: "TRANSLATION ENGINE" }
                                StyledCombo {
                                    id: engineCombo
                                    Layout.fillWidth: true
                                    model: langCard.engineNames
                                    currentIndex: langCard.engineIdToIndex(settingsBackend.engine)
                                    onActivated: settingsBackend.engine = langCard.engineIds[currentIndex]
                                }
                                // Engine description badge
                                Text {
                                    Layout.fillWidth: true
                                    text: langCard.engineDefs[engineCombo.currentIndex].icon + "  " + langCard.engineDefs[engineCombo.currentIndex].desc
                                    font.pixelSize: t ? t.fontSizeXS : 10
                                    color: t ? t.textMuted : "#55556a"
                                    elide: Text.ElideRight
                                }
                            }

                            // Vertical divider
                            Rectangle {
                                Layout.preferredWidth: 1; Layout.fillHeight: true
                                color: t ? t.border1 : "#2e2e3e"
                            }

                            // Source lang
                            ColumnLayout {
                                spacing: 5; Layout.fillWidth: true
                                SectionLabel { text: "SOURCE LANGUAGE" }
                                StyledCombo {
                                    id: sourceLangCombo
                                    Layout.fillWidth: true
                                    model: langCard.langNames
                                    currentIndex: langCard.codeToIndex(langCard.langCodes, settingsBackend.sourceLang)
                                    onActivated: settingsBackend.sourceLang = langCard.langCodes[currentIndex]
                                }
                            }

                            Text {
                                text: "→"; font.pixelSize: 16; color: t ? t.textMuted : "#55556a"
                                Layout.alignment: Qt.AlignBottom; Layout.bottomMargin: 8
                            }

                            // Target lang
                            ColumnLayout {
                                spacing: 5; Layout.fillWidth: true
                                SectionLabel { text: "TARGET LANGUAGE" }
                                StyledCombo {
                                    id: targetLangCombo
                                    Layout.fillWidth: true
                                    model: langCard.targetLangNames
                                    currentIndex: langCard.codeToIndex(langCard.targetLangCodes, settingsBackend.targetLang)
                                    onActivated: settingsBackend.targetLang = langCard.targetLangCodes[currentIndex]
                                }
                            }
                        }

                        // Dynamic Engine Configuration Panel (Visible if selected engine requires settings)
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: t ? t.spaceMD : 12
                            visible: settingsBackend.engine !== "google" && settingsBackend.engine !== "lingva"

                            Rectangle {
                                Layout.fillWidth: true
                                height: 1
                                color: t ? t.border1 : "#2e2e3e"
                            }

                            RowLayout {
                                spacing: 6
                                Text {
                                    text: "⚙  " + langCard.engineDefs[engineCombo.currentIndex].name + " Configuration"
                                    font.pixelSize: t ? t.fontSizeSM : 12
                                    font.bold: true
                                    color: t ? t.accentLight : "#a89bf9"
                                }
                            }

                            // DeepL Settings
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 10
                                visible: settingsBackend.engine === "deepl"

                                InputField {
                                    label: "DeepL API Key"
                                    text: settingsBackend.deeplApiKey
                                    placeholder: "Authentication key (e.g. xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx:fx)"
                                    isPassword: true
                                    onEditingFinished: settingsBackend.deeplApiKey = newText
                                }
                            }

                            // OpenAI Settings
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 10
                                visible: settingsBackend.engine === "openai"

                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: t ? t.spaceMD : 12
                                    InputField {
                                        label: "API Key"
                                        text: settingsBackend.openaiApiKey
                                        placeholder: "sk-..."
                                        isPassword: true
                                        onEditingFinished: settingsBackend.openaiApiKey = newText
                                    }
                                    InputField {
                                        label: "Model Name"
                                        text: settingsBackend.openaiModel
                                        placeholder: "gpt-4o-mini or deepseek-chat"
                                        onEditingFinished: settingsBackend.openaiModel = newText
                                    }
                                }
                                InputField {
                                    label: "Base URL (Optional - set to https://api.deepseek.com/v1 for DeepSeek)"
                                    text: settingsBackend.openaiBaseUrl
                                    placeholder: "https://api.openai.com/v1"
                                    onEditingFinished: settingsBackend.openaiBaseUrl = newText
                                }
                            }

                            // Gemini Settings
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 10
                                visible: settingsBackend.engine === "gemini"

                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: t ? t.spaceMD : 12
                                    InputField {
                                        label: "Gemini API Key"
                                        text: settingsBackend.geminiApiKey
                                        placeholder: "AIzaSy..."
                                        isPassword: true
                                        onEditingFinished: settingsBackend.geminiApiKey = newText
                                    }
                                    InputField {
                                        label: "Model Name"
                                        text: settingsBackend.geminiModel
                                        placeholder: "gemini-2.0-flash"
                                        onEditingFinished: settingsBackend.geminiModel = newText
                                    }
                                }
                            }

                            // Local LLM Settings
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 10
                                visible: settingsBackend.engine === "local_llm"

                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: t ? t.spaceMD : 12
                                    InputField {
                                        label: "Ollama / LM Studio Base URL"
                                        text: settingsBackend.localLlmUrl
                                        placeholder: "http://localhost:11434/v1"
                                        onEditingFinished: settingsBackend.localLlmUrl = newText
                                    }
                                    InputField {
                                        label: "Model Name"
                                        text: settingsBackend.localLlmModel
                                        placeholder: "llama3, mistral, qwen2.5..."
                                        onEditingFinished: settingsBackend.localLlmModel = newText
                                    }
                                }
                            }

                            // LibreTranslate Settings
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 10
                                visible: settingsBackend.engine === "libretranslate"

                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: t ? t.spaceMD : 12
                                    InputField {
                                        label: "Server URL"
                                        text: settingsBackend.libretranslateUrl
                                        placeholder: "http://localhost:5000"
                                        onEditingFinished: settingsBackend.libretranslateUrl = newText
                                    }
                                    InputField {
                                        label: "API Key (Optional)"
                                        text: settingsBackend.libretranslateApiKey
                                        placeholder: "Optional key"
                                        isPassword: true
                                        onEditingFinished: settingsBackend.libretranslateApiKey = newText
                                    }
                                }
                            }
                        }

                        // --- plugins.js translation toggle ---
                        Rectangle {
                            Layout.fillWidth: true
                            height: 1
                            color: t ? t.border1 : "#2e2e3e"
                        }
                        ToggleRow {
                            label: "Translate plugins.js"
                            desc: "Translates UI text stored inside js/plugins.js. Turn this off if translation breaks or crashes a specific game — some plugins keep logic-critical strings there that should stay untouched."
                            checked: settingsBackend.translatePluginsJs
                            onToggled: settingsBackend.translatePluginsJs = val
                        }
                    }
                }

                // --- START BUTTON ---
                AccentButton {
                    Layout.fillWidth: true
                    implicitHeight: 46
                    label: appBackend.isRunning ? "⏹  Stop Translation" : "▶  Start Translation"
                    enabled_: appBackend.projectPath.length > 0
                    onClicked: appBackend.isRunning ? appBackend.stopPipeline() : appBackend.startPipeline()
                    SequentialAnimation on opacity {
                        running: appBackend.isRunning; loops: Animation.Infinite
                        NumberAnimation { to: 0.7; duration: 900; easing.type: Easing.InOutSine }
                        NumberAnimation { to: 1.0; duration: 900; easing.type: Easing.InOutSine }
                    }
                }

                // --- PROGRESS CARD ---
                AppCard {
                    Layout.fillWidth: true; implicitHeight: 110
                    ColumnLayout {
                        anchors { fill: parent; margins: 20 }
                        spacing: t ? t.spaceMD : 12
                        RowLayout {
                            Layout.fillWidth: true
                            Text { text: "Progress"; font.pixelSize: 14; font.bold: true; color: t ? t.textPrimary : "#f0f0ff" }
                            Item { Layout.fillWidth: true }
                            Rectangle {
                                implicitHeight: 22; radius: 11
                                implicitWidth: stageText.implicitWidth + 20
                                color: Qt.rgba(124, 108, 248, 0.12)
                                border.color: Qt.rgba(124, 108, 248, 0.3); border.width: 1
                                Text {
                                    id: stageText; anchors.centerIn: parent
                                    text: appBackend.stageText; font.pixelSize: 11
                                    color: t ? t.accentLight : "#a89bf9"
                                }
                            }
                        }
                        Rectangle {
                            Layout.fillWidth: true; height: 8; radius: 4
                            color: t ? t.bg4 : "#2a2a3a"
                            Rectangle {
                                width: parent.width * (appBackend.progressTotal > 0 ? (appBackend.progressCurrent / appBackend.progressTotal) : 0.0)
                                height: parent.height; radius: parent.radius
                                gradient: Gradient {
                                    orientation: Gradient.Horizontal
                                    GradientStop { position: 0.0; color: t ? t.accentDark : "#5a4dd4" }
                                    GradientStop { position: 1.0; color: t ? t.accentLight : "#a89bf9" }
                                }
                                Behavior on width { NumberAnimation { duration: 300; easing.type: Easing.OutQuad } }
                            }
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            Text {
                                text: appBackend.progressText; font.pixelSize: t ? t.fontSizeSM : 12
                                color: t ? t.textMuted : "#55556a"; elide: Text.ElideRight; Layout.fillWidth: true
                            }
                            Text {
                                property int pct: appBackend.progressTotal > 0 ? Math.round(appBackend.progressCurrent * 100 / appBackend.progressTotal) : 0
                                text: pct + "%"; font.pixelSize: t ? t.fontSizeMD : 13; font.bold: true
                                color: pct > 0 ? (t ? t.accent : "#7c6cf8") : (t ? t.textMuted : "#55556a")
                            }
                        }
                    }
                }

                Item { height: 8 }
            }
        }
    }
}
