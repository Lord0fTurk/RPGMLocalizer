import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Controls.Material 2.15
import QtQuick.Layouts 1.15
import "../components"
import "../js/I18n.js" as I18n

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
            Text { text: toggleRowComp.desc; font.pixelSize: 11; color: t ? t.textSecondary : "#9090b8"; opacity: 0.85; visible: text.length > 0; wrapMode: Text.WordWrap; Layout.fillWidth: true }
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
                        Text { text: localeManager.strings.home.header_title; font.pixelSize: 20; font.bold: true; color: t ? t.textPrimary : "#f0f0ff" }
                        Text { text: localeManager.strings.home.header_subtitle; font.pixelSize: t ? t.fontSizeSM : 12; color: t ? t.textMuted : "#55556a" }
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
                            Text { text: localeManager.strings.home.translating_badge; color: t ? t.success : "#4ade80"; font.pixelSize: t ? t.fontSizeSM : 12 }
                        }
                    }
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                Layout.margins: 28
                spacing: 18

                // --- DROP ZONE & PROJECT CARD ---
                AppCard {
                    id: dropCard
                    Layout.fillWidth: true
                    implicitHeight: appBackend.projectPath ? 120 : 104
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
                                appBackend.setProjectPath(drop.urls[0].toString())
                            }
                        }
                    }
                    RowLayout {
                        anchors { fill: parent; margins: 20 }
                        spacing: 18

                        // Status / Engine Icon
                        Rectangle {
                            width: 52; height: 52; radius: 14
                            color: appBackend.projectPath ? Qt.rgba(124, 108, 248, 0.16) : Qt.rgba(255,255,255,0.04)
                            border.color: appBackend.projectPath ? Qt.rgba(124, 108, 248, 0.4) : (t ? t.border1 : "#2e2e3e")
                            border.width: 1
                            Behavior on color { ColorAnimation { duration: t ? t.animMedium : 220 } }
                            Text {
                                anchors.centerIn: parent
                                text: appBackend.projectPath ? (appBackend.detectedEngine.length > 0 ? "🎮" : "📁") : "📂"
                                font.pixelSize: 22
                            }
                        }

                        // Project Info
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 4

                            RowLayout {
                                spacing: 8
                                Text {
                                    text: appBackend.projectPath ? appBackend.projectPath.split(/[/\\]/).pop() : localeManager.strings.home.drop_zone_title
                                    font.pixelSize: t ? t.fontSizeLG : 15
                                    font.bold: true
                                    color: t ? t.textPrimary : "#f0f0ff"
                                    elide: Text.ElideMiddle
                                }

                                // Engine badge
                                Rectangle {
                                    visible: appBackend.projectPath.length > 0 && appBackend.detectedEngine.length > 0
                                    implicitHeight: 22
                                    implicitWidth: engineBadgeText.implicitWidth + 14
                                    radius: 11
                                    color: Qt.rgba(124, 108, 248, 0.18)
                                    border.color: Qt.rgba(124, 108, 248, 0.4)
                                    border.width: 1

                                    Text {
                                        id: engineBadgeText
                                        anchors.centerIn: parent
                                        text: appBackend.detectedEngine
                                        font.pixelSize: 11
                                        font.bold: true
                                        color: t ? t.accentLight : "#a89bf9"
                                    }
                                }
                            }

                            Text {
                                text: appBackend.projectPath ? appBackend.projectPath : localeManager.strings.home.drop_zone_subtitle
                                font.pixelSize: t ? t.fontSizeSM : 12
                                color: t ? t.textMuted : "#55556a"
                                elide: Text.ElideMiddle
                                Layout.fillWidth: true
                            }
                        }

                        // Action Buttons
                        RowLayout {
                            spacing: 8

                            // Open folder button
                            Rectangle {
                                visible: appBackend.projectPath.length > 0
                                width: 36; height: 36; radius: 8
                                color: ofMouse.containsMouse ? (t ? t.bgHover : "#32324a") : (t ? t.bg4 : "#2a2a3a")
                                border.color: t ? t.border2 : "#3d3d55"; border.width: 1
                                Text { anchors.centerIn: parent; text: "📂"; font.pixelSize: 14 }
                                MouseArea {
                                    id: ofMouse; anchors.fill: parent; hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: appBackend.openProjectFolder()
                                }
                                ToolTip.visible: ofMouse.containsMouse
                                ToolTip.text: localeManager.strings.home.project_open_folder
                                ToolTip.delay: 350
                            }

                            // Copy path button
                            Rectangle {
                                visible: appBackend.projectPath.length > 0
                                width: 36; height: 36; radius: 8
                                color: cpMouse.containsMouse ? (t ? t.bgHover : "#32324a") : (t ? t.bg4 : "#2a2a3a")
                                border.color: t ? t.border2 : "#3d3d55"; border.width: 1
                                Text { anchors.centerIn: parent; text: "📋"; font.pixelSize: 13 }
                                MouseArea {
                                    id: cpMouse; anchors.fill: parent; hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: {
                                        appBackend.copyToClipboard(appBackend.projectPath)
                                        toast.show("info", localeManager.strings.console.copied_label, appBackend.projectPath)
                                    }
                                }
                                ToolTip.visible: cpMouse.containsMouse
                                ToolTip.text: localeManager.strings.home.project_copy_path
                                ToolTip.delay: 350
                            }

                            // Clear button
                            Rectangle {
                                visible: appBackend.projectPath.length > 0
                                width: 36; height: 36; radius: 8
                                color: clMouse.containsMouse ? Qt.rgba(248, 113, 113, 0.15) : (t ? t.bg4 : "#2a2a3a")
                                border.color: clMouse.containsMouse ? (t ? t.danger : "#f87171") : (t ? t.border2 : "#3d3d55"); border.width: 1
                                Text { anchors.centerIn: parent; text: "✕"; font.pixelSize: 12; color: clMouse.containsMouse ? (t ? t.danger : "#f87171") : (t ? t.textSecondary : "#9090b8") }
                                MouseArea {
                                    id: clMouse; anchors.fill: parent; hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: appBackend.clearProjectPath()
                                }
                                ToolTip.visible: clMouse.containsMouse
                                ToolTip.text: localeManager.strings.home.project_clear_button
                                ToolTip.delay: 350
                            }

                            GhostButton {
                                label: localeManager.strings.home.browse_button
                                implicitWidth: 92
                                onClicked: appBackend.selectProjectDirectory()
                            }
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
                        { id: "google",         name: "Google Translate",   icon: "🌐", desc: localeManager.strings.home.engine_desc_google },
                        { id: "lingva",         name: "Lingva",             icon: "🔄", desc: localeManager.strings.home.engine_desc_lingva },
                        { id: "deepl",          name: "DeepL",              icon: "🎯", desc: localeManager.strings.home.engine_desc_deepl },
                        { id: "openai",         name: "OpenAI / ChatGPT",   icon: "🤖", desc: localeManager.strings.home.engine_desc_openai },
                        { id: "deepseek",       name: "DeepSeek",           icon: "🐳", desc: localeManager.strings.home.engine_desc_deepseek },
                        { id: "gemini",         name: "Google Gemini",      icon: "✨", desc: localeManager.strings.home.engine_desc_gemini },
                        { id: "local_llm",      name: "Local LLM (Ollama)", icon: "🦙", desc: localeManager.strings.home.engine_desc_local_llm },
                        { id: "libretranslate", name: "LibreTranslate",     icon: "🔓", desc: localeManager.strings.home.engine_desc_libretranslate },
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
                            spacing: t ? t.spaceMD : 14

                            // Engine selector
                            ColumnLayout {
                                spacing: 6
                                Layout.preferredWidth: 260
                                SectionLabel { text: localeManager.strings.home.section_engine }
                                StyledCombo {
                                    id: engineCombo
                                    Layout.fillWidth: true
                                    model: langCard.engineNames
                                    currentIndex: langCard.engineIdToIndex(settingsBackend.engine)
                                    onActivated: (index) => { settingsBackend.engine = langCard.engineIds[index] }
                                }
                                // Engine description badge
                                Rectangle {
                                    Layout.fillWidth: true
                                    implicitHeight: engDescTxt.implicitHeight + 8
                                    radius: 6
                                    color: Qt.rgba(255, 255, 255, 0.04)
                                    border.color: t ? t.border1 : "#2e2e3e"
                                    border.width: 1
                                    RowLayout {
                                        anchors { fill: parent; leftMargin: 8; rightMargin: 8 }
                                        Text {
                                            id: engDescTxt
                                            text: langCard.engineDefs[engineCombo.currentIndex].icon + "  "
                                                  + langCard.engineDefs[engineCombo.currentIndex].desc
                                                  + (langCard.engineDefs[engineCombo.currentIndex].wip ? localeManager.strings.home.engine_wip_suffix : "")
                                            font.pixelSize: 11
                                            color: t ? t.textSecondary : "#9090b8"
                                            elide: Text.ElideRight
                                            Layout.fillWidth: true
                                        }
                                    }
                                }
                            }

                            // Vertical divider
                            Rectangle {
                                Layout.preferredWidth: 1; Layout.fillHeight: true
                                Layout.topMargin: 4; Layout.bottomMargin: 4
                                color: t ? t.border1 : "#2e2e3e"
                            }

                            // Source lang
                            ColumnLayout {
                                spacing: 6; Layout.fillWidth: true
                                SectionLabel { text: localeManager.strings.home.section_source_lang }
                                StyledCombo {
                                    id: sourceLangCombo
                                    Layout.fillWidth: true
                                    model: langCard.langNames
                                    currentIndex: langCard.codeToIndex(langCard.langCodes, settingsBackend.sourceLang)
                                    onActivated: (index) => { settingsBackend.sourceLang = langCard.langCodes[index] }
                                }
                            }

                            // Swap Languages Button
                            Rectangle {
                                id: swapBtn
                                implicitWidth: 36; implicitHeight: 36; radius: 18
                                Layout.alignment: Qt.AlignBottom; Layout.bottomMargin: 1
                                color: swapMouse.containsMouse ? (t ? t.bgHover : "#32324a") : (t ? t.bg4 : "#2a2a3a")
                                border.color: swapMouse.containsMouse ? (t ? t.accent : "#7c6cf8") : (t ? t.border2 : "#3d3d55")
                                border.width: 1
                                Behavior on color { ColorAnimation { duration: 120 } }
                                Behavior on border.color { ColorAnimation { duration: 120 } }

                                Text {
                                    anchors.centerIn: parent
                                    text: "⇄"
                                    font.pixelSize: 16
                                    font.bold: true
                                    color: swapMouse.containsMouse ? (t ? t.accentLight : "#a89bf9") : (t ? t.textSecondary : "#9090b8")
                                }
                                MouseArea {
                                    id: swapMouse; anchors.fill: parent; hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: {
                                        var src = settingsBackend.sourceLang
                                        var tgt = settingsBackend.targetLang
                                        if (src !== "auto") {
                                            settingsBackend.sourceLang = tgt
                                            settingsBackend.targetLang = src
                                        } else {
                                            settingsBackend.sourceLang = tgt
                                            settingsBackend.targetLang = "en"
                                        }
                                    }
                                }
                                ToolTip.visible: swapMouse.containsMouse
                                ToolTip.text: localeManager.strings.home.swap_languages
                                ToolTip.delay: 300
                            }

                            // Target lang
                            ColumnLayout {
                                spacing: 6; Layout.fillWidth: true
                                SectionLabel { text: localeManager.strings.home.section_target_lang }
                                StyledCombo {
                                    id: targetLangCombo
                                    Layout.fillWidth: true
                                    model: langCard.targetLangNames
                                    currentIndex: langCard.codeToIndex(langCard.targetLangCodes, settingsBackend.targetLang)
                                    onActivated: (index) => { settingsBackend.targetLang = langCard.targetLangCodes[index] }
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
                                    text: I18n.format(localeManager.strings.home.engine_config_title, {name: langCard.engineDefs[engineCombo.currentIndex].name})
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
                                    label: localeManager.strings.home.deepl_api_key_label
                                    text: settingsBackend.deeplApiKey
                                    placeholder: "Authentication key (e.g. xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx:fx)"
                                    isPassword: true
                                    onEditingFinished: (newText) => { settingsBackend.deeplApiKey = newText }
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
                                        label: localeManager.strings.home.api_key_label
                                        text: settingsBackend.openaiApiKey
                                        placeholder: "sk-..."
                                        isPassword: true
                                        onEditingFinished: (newText) => { settingsBackend.openaiApiKey = newText }
                                    }
                                    InputField {
                                        label: localeManager.strings.home.model_name_label
                                        text: settingsBackend.openaiModel
                                        placeholder: "gpt-4o-mini or deepseek-chat"
                                        onEditingFinished: (newText) => { settingsBackend.openaiModel = newText }
                                    }
                                }
                                InputField {
                                    label: localeManager.strings.home.openai_base_url_label
                                    text: settingsBackend.openaiBaseUrl
                                    placeholder: "https://api.openai.com/v1"
                                    onEditingFinished: (newText) => { settingsBackend.openaiBaseUrl = newText }
                                }
                            }

                            // DeepSeek Settings
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 10
                                visible: settingsBackend.engine === "deepseek"

                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: t ? t.spaceMD : 12
                                    InputField {
                                        label: localeManager.strings.home.deepseek_api_key_label
                                        text: settingsBackend.deepseekApiKey
                                        placeholder: "sk-..."
                                        isPassword: true
                                        onEditingFinished: (newText) => { settingsBackend.deepseekApiKey = newText }
                                    }
                                    InputField {
                                        label: localeManager.strings.home.model_name_label
                                        text: settingsBackend.deepseekModel
                                        placeholder: "deepseek-chat"
                                        onEditingFinished: (newText) => { settingsBackend.deepseekModel = newText }
                                    }
                                }
                                InputField {
                                    label: localeManager.strings.home.base_url_label
                                    text: settingsBackend.deepseekBaseUrl
                                    placeholder: "https://api.deepseek.com/v1"
                                    onEditingFinished: (newText) => { settingsBackend.deepseekBaseUrl = newText }
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
                                        label: localeManager.strings.home.gemini_api_key_label
                                        text: settingsBackend.geminiApiKey
                                        placeholder: "AIzaSy..."
                                        isPassword: true
                                        onEditingFinished: (newText) => { settingsBackend.geminiApiKey = newText }
                                    }
                                    InputField {
                                        label: localeManager.strings.home.model_name_label
                                        text: settingsBackend.geminiModel
                                        placeholder: "gemini-2.0-flash"
                                        onEditingFinished: (newText) => { settingsBackend.geminiModel = newText }
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
                                        label: localeManager.strings.home.local_llm_base_url_label
                                        text: settingsBackend.localLlmUrl
                                        placeholder: "http://localhost:11434/v1"
                                        onEditingFinished: (newText) => { settingsBackend.localLlmUrl = newText }
                                    }
                                    InputField {
                                        label: localeManager.strings.home.model_name_label
                                        text: settingsBackend.localLlmModel
                                        placeholder: "llama3, mistral, qwen2.5..."
                                        onEditingFinished: (newText) => { settingsBackend.localLlmModel = newText }
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
                                        label: localeManager.strings.home.server_url_label
                                        text: settingsBackend.libretranslateUrl
                                        placeholder: "http://localhost:5000"
                                        onEditingFinished: (newText) => { settingsBackend.libretranslateUrl = newText }
                                    }
                                    InputField {
                                        label: localeManager.strings.home.api_key_optional_label
                                        text: settingsBackend.libretranslateApiKey
                                        placeholder: "Optional key"
                                        isPassword: true
                                        onEditingFinished: (newText) => { settingsBackend.libretranslateApiKey = newText }
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
                            label: localeManager.strings.home.translate_plugins_label
                            desc: localeManager.strings.home.translate_plugins_desc
                            checked: settingsBackend.translatePluginsJs
                            onToggled: (val) => { settingsBackend.translatePluginsJs = val }
                        }
                    }
                }

                // --- PRIMARY ACTION ROW ---
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 16

                    AccentButton {
                        Layout.preferredWidth: 360
                        Layout.preferredHeight: 46
                        label: appBackend.isRunning ? localeManager.strings.home.stop_translation_button : localeManager.strings.home.start_translation_button
                        enabled_: appBackend.projectPath.length > 0
                        onClicked: appBackend.isRunning ? appBackend.stopPipeline() : appBackend.startPipeline()
                        SequentialAnimation on opacity {
                            running: appBackend.isRunning; loops: Animation.Infinite
                            NumberAnimation { to: 0.7; duration: 900; easing.type: Easing.InOutSine }
                            NumberAnimation { to: 1.0; duration: 900; easing.type: Easing.InOutSine }
                        }
                    }

                    Item { Layout.fillWidth: true }

                    // Project Engine & State Badge
                    Rectangle {
                        visible: appBackend.projectPath.length > 0
                        implicitHeight: 38
                        implicitWidth: engineStatRow.implicitWidth + 24
                        radius: 19
                        color: t ? t.bg3 : "#22222f"
                        border.color: t ? t.border1 : "#2e2e3e"
                        border.width: 1

                        RowLayout {
                            id: engineStatRow
                            anchors.centerIn: parent
                            spacing: 10

                            Text {
                                text: appBackend.detectedEngine.length > 0 ? ("🎮 " + appBackend.detectedEngine) : "📁 Proje Hazır"
                                font.pixelSize: t ? t.fontSizeSM : 12
                                font.bold: true
                                color: t ? t.accentLight : "#a89bf9"
                            }
                            Rectangle { width: 1; height: 14; color: t ? t.border2 : "#3d3d55" }
                            Text {
                                text: appBackend.stageText
                                font.pixelSize: 11
                                color: appBackend.isRunning ? (t ? t.success : "#4ade80") : (t ? t.textMuted : "#55556a")
                            }
                        }
                    }
                }

                // --- PROGRESS CARD ---
                AppCard {
                    Layout.fillWidth: true
                    implicitHeight: appBackend.isRunning || appBackend.progressTotal > 0 ? 110 : 76
                    Behavior on implicitHeight { NumberAnimation { duration: 200; easing.type: Easing.OutQuad } }

                    ColumnLayout {
                        anchors { fill: parent; margins: 18 }
                        spacing: t ? t.spaceMD : 12

                        RowLayout {
                            Layout.fillWidth: true
                            Text { text: localeManager.strings.home.progress_label; font.pixelSize: 14; font.bold: true; color: t ? t.textPrimary : "#f0f0ff" }
                            Item { Layout.fillWidth: true }
                            Rectangle {
                                implicitHeight: 22; radius: 11
                                implicitWidth: stageText.implicitWidth + 20
                                color: appBackend.isRunning ? Qt.rgba(74, 222, 128, 0.15) : Qt.rgba(124, 108, 248, 0.12)
                                border.color: appBackend.isRunning ? Qt.rgba(74, 222, 128, 0.4) : Qt.rgba(124, 108, 248, 0.3)
                                border.width: 1
                                Text {
                                    id: stageText; anchors.centerIn: parent
                                    text: appBackend.stageText; font.pixelSize: 11
                                    font.bold: appBackend.isRunning
                                    color: appBackend.isRunning ? (t ? t.success : "#4ade80") : (t ? t.accentLight : "#a89bf9")
                                }
                            }
                        }

                        ShimmerProgressBar {
                            themeObj: t
                            visible: appBackend.isRunning || appBackend.progressTotal > 0
                            value: appBackend.progressTotal > 0 ? (appBackend.progressCurrent / appBackend.progressTotal) : 0.0
                            statusText: appBackend.progressText
                        }

                        // Compact idle message
                        RowLayout {
                            visible: !appBackend.isRunning && appBackend.progressTotal === 0
                            spacing: 8
                            Rectangle { width: 6; height: 6; radius: 3; color: t ? t.textMuted : "#55556a" }
                            Text {
                                text: appBackend.projectPath ? (appBackend.detectedEngine.length > 0 ? (appBackend.detectedEngine + " — " + appBackend.progressText) : appBackend.progressText) : localeManager.strings.home.drop_zone_title
                                font.pixelSize: t ? t.fontSizeSM : 12
                                color: t ? t.textMuted : "#55556a"
                            }
                        }
                    }
                }

                Item { height: 8 }
            }
        }
    }
}
