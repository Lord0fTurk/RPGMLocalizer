import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Controls.Material 2.15
import QtQuick.Layouts 1.15

import "../js/I18n.js" as I18n

Popup {
    id: root
    property var themeObj: null
    property var t: themeObj

    signal startRequested(var options)

    // Dynamic scope options (All, File, Category, Filtered)
    property var scopeList: []

    // ---- Styled ComboBox (Dark theme, rounded corners, clean dropdown) ----
    component StyledCombo: ComboBox {
        id: styledCombo
        Material.theme: Material.Dark
        implicitHeight: 36
        background: Rectangle {
            color: styledCombo.popup.visible ? (t ? t.bg4 : "#2a2a3a") : (styledCombo.hovered ? (t ? t.bgHover : "#32324a") : (t ? t.bg4 : "#22222f"))
            border.color: styledCombo.popup.visible ? (t ? t.accent : "#7c6cf8") : (t ? t.border2 : "#3d3d55")
            border.width: 1
            radius: 8
            Behavior on color { ColorAnimation { duration: t ? t.animFast : 130 } }
            Behavior on border.color { ColorAnimation { duration: t ? t.animFast : 130 } }
        }
        contentItem: Text {
            leftPadding: 12
            rightPadding: styledCombo.indicator.width + 8
            text: styledCombo.displayText
            color: t ? t.textPrimary : "#ffffff"
            font.pixelSize: 12
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }
        indicator: Text {
            x: styledCombo.width - width - 10
            y: (styledCombo.height - height) / 2
            text: "▾"
            color: t ? t.textSecondary : "#bbbbd0"
            font.pixelSize: 11
            rotation: styledCombo.popup.visible ? 180 : 0
            Behavior on rotation { NumberAnimation { duration: 150 } }
        }
        popup: Popup {
            y: styledCombo.height + 4
            width: styledCombo.width
            implicitHeight: contentItem.implicitHeight
            padding: 4
            background: Rectangle {
                color: t ? t.bg3 : "#22222f"
                border.color: t ? t.border2 : "#3d3d55"
                border.width: 1
                radius: t ? t.radiusMD : 10
            }
            contentItem: ListView {
                clip: true
                implicitHeight: Math.min(contentHeight, 280)
                model: styledCombo.delegateModel
                ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
            }
        }
        delegate: ItemDelegate {
            width: styledCombo.width - 8
            highlighted: styledCombo.highlightedIndex === index
            contentItem: Text {
                text: styledCombo.textRole ? modelData[styledCombo.textRole] : modelData
                font.pixelSize: 12
                leftPadding: 8
                color: highlighted ? "white" : (t ? t.textSecondary : "#bbbbd0")
                verticalAlignment: Text.AlignVCenter
                elide: Text.ElideRight
            }
            background: Rectangle {
                color: highlighted ? (t ? t.accentGlow : "#1c1c30") : "transparent"
                radius: t ? t.radiusSM : 6
            }
        }
    }

    parent: Overlay.overlay
    anchors.centerIn: parent
    width: 520
    padding: 0
    height: Math.min(dialogLayout.implicitHeight + 40, 640)
    Behavior on height { NumberAnimation { duration: 160; easing.type: Easing.OutQuad } }
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

    // Supported lists
    readonly property var sourceLanguages: [
        { code: "auto",  name: localeManager.strings.auto_translate.lang_names.auto },
        { code: "ja",    name: localeManager.strings.auto_translate.lang_names.ja },
        { code: "en",    name: localeManager.strings.auto_translate.lang_names.en },
        { code: "ko",    name: localeManager.strings.auto_translate.lang_names.ko },
        { code: "zh-CN", name: localeManager.strings.auto_translate.lang_names["zh-CN"] },
        { code: "ru",    name: localeManager.strings.auto_translate.lang_names.ru },
        { code: "de",    name: localeManager.strings.auto_translate.lang_names.de },
        { code: "fr",    name: localeManager.strings.auto_translate.lang_names.fr },
        { code: "es",    name: localeManager.strings.auto_translate.lang_names.es }
    ]

    readonly property var targetLanguages: [
        { code: "tr",    name: localeManager.strings.auto_translate.lang_names.tr },
        { code: "en",    name: localeManager.strings.auto_translate.lang_names.en },
        { code: "de",    name: localeManager.strings.auto_translate.lang_names.de },
        { code: "fr",    name: localeManager.strings.auto_translate.lang_names.fr },
        { code: "es",    name: localeManager.strings.auto_translate.lang_names.es },
        { code: "ru",    name: localeManager.strings.auto_translate.lang_names.ru },
        { code: "it",    name: localeManager.strings.auto_translate.lang_names.it },
        { code: "pt",    name: localeManager.strings.auto_translate.lang_names.pt }
    ]

    readonly property var engines: [
        { id: "google",     name: localeManager.strings.auto_translate.engine_names.google },
        { id: "gemini",     name: localeManager.strings.auto_translate.engine_names.gemini },
        { id: "deepl",      name: localeManager.strings.auto_translate.engine_names.deepl },
        { id: "openai",     name: localeManager.strings.auto_translate.engine_names.openai },
        { id: "deepseek",   name: localeManager.strings.auto_translate.engine_names.deepseek },
        { id: "local_llm",  name: localeManager.strings.auto_translate.engine_names.local_llm }
    ]

    readonly property var geminiSafetyOptions: [
        { key: "BLOCK_NONE",      name: localeManager.strings.auto_translate.safety_block_none },
        { key: "BLOCK_ONLY_HIGH", name: localeManager.strings.auto_translate.safety_block_only_high },
        { key: "STANDARD",        name: localeManager.strings.auto_translate.safety_standard }
    ]

    function refreshScopeOptions() {
        var opts = []

        // 1. All
        var allCount = editorBackend.getScopeUntranslatedCount("all")
        opts.push({
            id: "all",
            name: "🌐 " + localeManager.strings.auto_translate.scope_all + " (" + allCount + ")",
            count: allCount
        })

        // 2. Active File (if filtered)
        var curFile = editorBackend.activeFileFilter
        if (curFile && curFile !== "all" && curFile !== "Tüm Dosyalar") {
            var fileCount = editorBackend.getScopeUntranslatedCount("file")
            opts.push({
                id: "file",
                name: "📁 " + localeManager.strings.auto_translate.scope_file + " [" + curFile + "] (" + fileCount + ")",
                count: fileCount
            })
        }

        // 3. Active Category (if filtered)
        var curCat = editorBackend.activeCategoryFilter
        if (curCat && curCat !== "all") {
            var catCount = editorBackend.getScopeUntranslatedCount("category")
            opts.push({
                id: "category",
                name: "🏷️ " + localeManager.strings.auto_translate.scope_category + " [" + curCat + "] (" + catCount + ")",
                count: catCount
            })
        }

        // 4. Search Filter (if any)
        var curSearch = editorBackend.activeSearchQuery
        if (curSearch && curSearch.trim().length > 0) {
            var filtCount = editorBackend.getScopeUntranslatedCount("filtered")
            opts.push({
                id: "filtered",
                name: "🔍 " + localeManager.strings.auto_translate.scope_filtered + " (" + filtCount + ")",
                count: filtCount
            })
        }

        root.scopeList = opts

        // If an active file is chosen, default to file scope, otherwise all
        if (opts.length > 1 && curFile && curFile !== "all" && curFile !== "Tüm Dosyalar") {
            scopeCombo.currentIndex = 1
        } else {
            scopeCombo.currentIndex = 0
        }
    }

    function openDialog() {
        // Sync inputs from settings backend
        var currentSrc = settingsBackend.sourceLang || "auto"
        for (var i = 0; i < sourceLanguages.length; i++) {
            if (sourceLanguages[i].code === currentSrc) {
                srcCombo.currentIndex = i
                break
            }
        }

        var currentTgt = settingsBackend.targetLang || "tr"
        for (var j = 0; j < targetLanguages.length; j++) {
            if (targetLanguages[j].code === currentTgt) {
                tgtCombo.currentIndex = j
                break
            }
        }

        // Default to Google Web (free, no API key)
        engineCombo.currentIndex = 0

        geminiKeyInput.text = settingsBackend.geminiApiKey || ""
        geminiModelInput.text = settingsBackend.geminiModel || "gemini-2.5-flash"
        var currentSafety = settingsBackend.geminiSafetySettings || "BLOCK_NONE"
        for (var s = 0; s < geminiSafetyOptions.length; s++) {
            if (geminiSafetyOptions[s].key === currentSafety) {
                geminiSafetyCombo.currentIndex = s
                break
            }
        }

        deeplKeyInput.text = settingsBackend.deeplApiKey || ""
        openaiKeyInput.text = settingsBackend.openaiApiKey || ""
        deepseekKeyInput.text = settingsBackend.deepseekApiKey || ""

        refreshScopeOptions()
        open()
    }

    ColumnLayout {
        id: dialogLayout
        anchors.fill: parent
        anchors.margins: 20
        spacing: 14

        // --- 1. Header (Fixed / Pinned) ---
        RowLayout {
            id: headerRow
            Layout.fillWidth: true
            Text {
                text: localeManager.strings.auto_translate.header_title
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

        // --- 2. Body / Form Fields (Scrollable as needed) ---
        ScrollView {
            id: formScroll
            Layout.fillWidth: true
            Layout.fillHeight: true
            implicitHeight: formCol.implicitHeight
            clip: true
            contentWidth: availableWidth
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
            ScrollBar.vertical: ScrollBar {
                policy: ScrollBar.AsNeeded
                width: 6
                contentItem: Rectangle {
                    implicitWidth: 6
                    radius: 3
                    color: t ? t.accent : "#7c6cf8"
                    opacity: 0.6
                }
                background: Rectangle { color: "transparent" }
            }

            ColumnLayout {
                id: formCol
                width: formScroll.availableWidth - (formScroll.ScrollBar.vertical.visible ? 8 : 0)
                spacing: t ? t.spaceLG : 14

                // --- Info Banner ---
                Rectangle {
                    Layout.fillWidth: true
                    implicitHeight: bannerRow.implicitHeight + 20
                    radius: 8
                    color: Qt.rgba(124, 108, 248, 0.12)
                    border.color: Qt.rgba(124, 108, 248, 0.3)
                    border.width: 1

                    RowLayout {
                        id: bannerRow
                        anchors.fill: parent
                        anchors.margins: 10
                        spacing: 8
                        Text {
                            text: "📋"
                            font.pixelSize: 14
                            Layout.alignment: Qt.AlignTop
                        }
                        Text {
                            text: {
                                var count = (root.scopeList.length > scopeCombo.currentIndex && scopeCombo.currentIndex >= 0)
                                    ? root.scopeList[scopeCombo.currentIndex].count
                                    : editorBackend.untranslatedCount
                                return I18n.format(localeManager.strings.auto_translate.info_banner, {count: count})
                            }
                            font.pixelSize: 12
                            color: t ? t.textPrimary : "#ffffff"
                            wrapMode: Text.Wrap
                            Layout.fillWidth: true
                        }
                    }
                }

                // --- Scope Selector ---
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 4
                    Text {
                        text: localeManager.strings.auto_translate.scope_label
                        font.pixelSize: 12
                        font.bold: true
                        color: t ? t.textSecondary : "#bbbbd0"
                    }
                    StyledCombo {
                        id: scopeCombo
                        Layout.fillWidth: true
                        model: root.scopeList
                        textRole: "name"
                    }
                }

                // --- Language Selectors ---
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 12

                    // Source Language
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 4
                        Text {
                            text: localeManager.strings.auto_translate.source_lang_label
                            font.pixelSize: 12
                            font.bold: true
                            color: t ? t.textSecondary : "#bbbbd0"
                        }
                        StyledCombo {
                            id: srcCombo
                            Layout.fillWidth: true
                            model: root.sourceLanguages
                            textRole: "name"
                        }
                    }

                    // Target Language
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 4
                        Text {
                            text: localeManager.strings.auto_translate.target_lang_label
                            font.pixelSize: 12
                            font.bold: true
                            color: t ? t.textSecondary : "#bbbbd0"
                        }
                        StyledCombo {
                            id: tgtCombo
                            Layout.fillWidth: true
                            model: root.targetLanguages
                            textRole: "name"
                        }
                    }
                }

                // --- Translation Engine ---
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 4
                    Text {
                        text: localeManager.strings.auto_translate.engine_label
                        font.pixelSize: 12
                        font.bold: true
                        color: t ? t.textSecondary : "#bbbbd0"
                    }
                    StyledCombo {
                        id: engineCombo
                        Layout.fillWidth: true
                        model: root.engines
                        textRole: "name"
                    }
                }

                // --- Dynamic Engine Settings ---
                // 1. Google Web Note
                Rectangle {
                    Layout.fillWidth: true
                    height: 48
                    radius: 8
                    color: t ? t.bg2 : "#1a1a24"
                    border.color: t ? t.border1 : "#2e2e3e"
                    visible: engineCombo.currentIndex === 0 // Google

                    RowLayout {
                        anchors.fill: parent
                        anchors.margins: 10
                        spacing: 8
                        Text { text: "ℹ️"; font.pixelSize: 14 }
                        Text {
                            text: localeManager.strings.auto_translate.google_note
                            font.pixelSize: 11
                            color: t ? t.textSecondary : "#9a9ab2"
                            wrapMode: Text.Wrap
                            Layout.fillWidth: true
                        }
                    }
                }

                // 2. Gemini Settings
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 8
                    visible: engineCombo.currentIndex === 1 // Gemini

                    ColumnLayout {
                        Layout.fillWidth: true; spacing: 2
                        Text { text: localeManager.strings.auto_translate.gemini_api_key_label; font.pixelSize: 11; color: t ? t.textSecondary : "#bbbbd0" }
                        Rectangle {
                            Layout.fillWidth: true; height: 32; radius: 6
                            color: t ? t.bg2 : "#1a1a24"
                            border.color: geminiKeyInput.activeFocus ? (t ? t.accent : "#7c6cf8") : (t ? t.border1 : "#2e2e3e")
                            TextInput {
                                id: geminiKeyInput
                                anchors { fill: parent; leftMargin: 8; rightMargin: 8 }
                                verticalAlignment: TextInput.AlignVCenter
                                color: t ? t.textPrimary : "#ffffff"
                                font.pixelSize: 12
                                echoMode: TextInput.Password
                                selectByMouse: true
                            }
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8

                        ColumnLayout {
                            Layout.fillWidth: true; spacing: 2
                            Text { text: localeManager.strings.auto_translate.model_label; font.pixelSize: 11; color: t ? t.textSecondary : "#bbbbd0" }
                            Rectangle {
                                Layout.fillWidth: true; height: 32; radius: 6
                                color: t ? t.bg2 : "#1a1a24"
                                border.color: geminiModelInput.activeFocus ? (t ? t.accent : "#7c6cf8") : (t ? t.border1 : "#2e2e3e")
                                TextInput {
                                    id: geminiModelInput
                                    anchors { fill: parent; leftMargin: 8; rightMargin: 8 }
                                    verticalAlignment: TextInput.AlignVCenter
                                    color: t ? t.textPrimary : "#ffffff"
                                    font.pixelSize: 12
                                    selectByMouse: true
                                }
                            }
                        }

                        ColumnLayout {
                            Layout.fillWidth: true; spacing: 2
                            Text { text: localeManager.strings.auto_translate.safety_filter_label; font.pixelSize: 11; color: t ? t.textSecondary : "#bbbbd0" }
                            StyledCombo {
                                id: geminiSafetyCombo
                                Layout.fillWidth: true
                                model: root.geminiSafetyOptions
                                textRole: "name"
                            }
                        }
                    }
                }

                // 3. DeepL Settings
                ColumnLayout {
                    Layout.fillWidth: true; spacing: 4
                    visible: engineCombo.currentIndex === 2 // DeepL
                    Text { text: localeManager.strings.auto_translate.deepl_api_key_label; font.pixelSize: 11; color: t ? t.textSecondary : "#bbbbd0" }
                    Rectangle {
                        Layout.fillWidth: true; height: 32; radius: 6
                        color: t ? t.bg2 : "#1a1a24"
                        border.color: deeplKeyInput.activeFocus ? (t ? t.accent : "#7c6cf8") : (t ? t.border1 : "#2e2e3e")
                        TextInput {
                            id: deeplKeyInput
                            anchors { fill: parent; leftMargin: 8; rightMargin: 8 }
                            verticalAlignment: TextInput.AlignVCenter
                            color: t ? t.textPrimary : "#ffffff"
                            font.pixelSize: 12
                            echoMode: TextInput.Password
                            selectByMouse: true
                        }
                    }
                }

                // 4. OpenAI Settings
                ColumnLayout {
                    Layout.fillWidth: true; spacing: 4
                    visible: engineCombo.currentIndex === 3 // OpenAI
                    Text { text: localeManager.strings.auto_translate.openai_api_key_label; font.pixelSize: 11; color: t ? t.textSecondary : "#bbbbd0" }
                    Rectangle {
                        Layout.fillWidth: true; height: 32; radius: 6
                        color: t ? t.bg2 : "#1a1a24"
                        border.color: openaiKeyInput.activeFocus ? (t ? t.accent : "#7c6cf8") : (t ? t.border1 : "#2e2e3e")
                        TextInput {
                            id: openaiKeyInput
                            anchors { fill: parent; leftMargin: 8; rightMargin: 8 }
                            verticalAlignment: TextInput.AlignVCenter
                            color: t ? t.textPrimary : "#ffffff"
                            font.pixelSize: 12
                            echoMode: TextInput.Password
                            selectByMouse: true
                        }
                    }
                }

                // 5. DeepSeek Settings
                ColumnLayout {
                    Layout.fillWidth: true; spacing: 4
                    visible: engineCombo.currentIndex === 4 // DeepSeek
                    Text { text: localeManager.strings.auto_translate.deepseek_api_key_label; font.pixelSize: 11; color: t ? t.textSecondary : "#bbbbd0" }
                    Rectangle {
                        Layout.fillWidth: true; height: 32; radius: 6
                        color: t ? t.bg2 : "#1a1a24"
                        border.color: deepseekKeyInput.activeFocus ? (t ? t.accent : "#7c6cf8") : (t ? t.border1 : "#2e2e3e")
                        TextInput {
                            id: deepseekKeyInput
                            anchors { fill: parent; leftMargin: 8; rightMargin: 8 }
                            verticalAlignment: TextInput.AlignVCenter
                            color: t ? t.textPrimary : "#ffffff"
                            font.pixelSize: 12
                            echoMode: TextInput.Password
                            selectByMouse: true
                        }
                    }
                }

                // 6. Local LLM Settings
                ColumnLayout {
                    Layout.fillWidth: true; spacing: 4
                    visible: engineCombo.currentIndex === 5 // Local LLM
                    Text {
                        text: localeManager.strings.auto_translate.local_llm_note
                        font.pixelSize: 11
                        color: t ? t.textSecondary : "#9a9ab2"
                    }
                }
            }
        }

        // --- 3. Action Buttons (Fixed Footer) ---
        RowLayout {
            id: footerRow
            Layout.fillWidth: true
            spacing: 10

            Item { Layout.fillWidth: true }

            // Cancel Button
            Rectangle {
                width: 90; height: 36; radius: 8
                color: cancelMouse.containsMouse ? Qt.rgba(255,255,255,0.08) : "transparent"
                border.color: t ? t.border1 : "#3d3d55"
                border.width: 1

                Text {
                    anchors.centerIn: parent
                    text: localeManager.strings.common.cancel
                    font.pixelSize: 13
                    color: t ? t.textSecondary : "#ffffff"
                }
                MouseArea {
                    id: cancelMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.close()
                }
            }

            // Start Translation Button
            Rectangle {
                width: 160; height: 36; radius: 8
                color: startMouse.containsMouse ? Qt.lighter(t ? t.accent : "#7c6cf8", 1.1) : (t ? t.accent : "#7c6cf8")

                RowLayout {
                    anchors.centerIn: parent
                    spacing: 6
                    Text { text: "🚀"; font.pixelSize: 13 }
                    Text {
                        text: localeManager.strings.auto_translate.start_button
                        font.pixelSize: 13
                        font.bold: true
                        color: "#ffffff"
                    }
                }

                MouseArea {
                    id: startMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        var selSrc = root.sourceLanguages[srcCombo.currentIndex].code
                        var selTgt = root.targetLanguages[tgtCombo.currentIndex].code
                        var selEng = root.engines[engineCombo.currentIndex].id
                        var selScope = (root.scopeList.length > scopeCombo.currentIndex && scopeCombo.currentIndex >= 0)
                            ? root.scopeList[scopeCombo.currentIndex].id
                            : "all"

                        var opts = {
                            "source_lang": selSrc,
                            "target_lang": selTgt,
                            "engine": selEng,
                            "scope": selScope
                        }

                        if (selEng === "gemini") {
                            opts["gemini_api_key"] = geminiKeyInput.text.trim()
                            opts["gemini_model"] = geminiModelInput.text.trim() || "gemini-2.5-flash"
                            opts["gemini_safety_settings"] = root.geminiSafetyOptions[geminiSafetyCombo.currentIndex].key
                        } else if (selEng === "deepl") {
                            opts["deepl_api_key"] = deeplKeyInput.text.trim()
                        } else if (selEng === "openai") {
                            opts["openai_api_key"] = openaiKeyInput.text.trim()
                        } else if (selEng === "deepseek") {
                            opts["deepseek_api_key"] = deepseekKeyInput.text.trim()
                        }

                        root.startRequested(opts)
                        root.close()
                    }
                }
            }
        }
    }
}
