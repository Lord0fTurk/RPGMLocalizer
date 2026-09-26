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

    // Reusable Card container
    component AppCard: Rectangle {
        color: t ? t.bg3 : "#22222f"
        border.color: t ? t.border1 : "#2e2e3e"
        border.width: 1
        radius: 12
    }

    property int animDotCount: 0
    Timer {
        interval: 400
        running: editorBackend.isScanning
        repeat: true
        onTriggered: root.animDotCount = (root.animDotCount + 1) % 4
    }
    function getAnimatedDots() {
        return animDotCount === 1 ? "." : (animDotCount === 2 ? ".." : (animDotCount === 3 ? "..." : ""))
    }

    // Initialize/scan on visit if project is selected and editor not yet loaded
    Component.onCompleted: {
        if (appBackend.projectPath && !editorBackend.projectLoaded && !editorBackend.isScanning) {
            editorBackend.scanOrLoadProject()
        }
    }

    function selectRow(entryId) {
        if (editorBackend.selectedEntry && editorBackend.selectedEntry.id && typeof transTextArea !== "undefined" && transTextArea.text !== (editorBackend.selectedEntry.translated_text || "")) {
            editorBackend.updateSelectedTranslation(transTextArea.text)
        }
        editorBackend.selectEntryById(entryId)
    }

    function changePage(newPage) {
        if (editorBackend.selectedEntry && editorBackend.selectedEntry.id && typeof transTextArea !== "undefined" && transTextArea.text !== (editorBackend.selectedEntry.translated_text || "")) {
            editorBackend.updateSelectedTranslation(transTextArea.text)
        }
        editorBackend.setPage(newPage)
    }

    // Commit any text still sitting in the detail editor (not yet applied via
    // Ctrl+Enter / row change) so a direct Save never silently drops it.
    readonly property bool hasPendingEdit: !!(editorBackend.selectedEntry && editorBackend.selectedEntry.id)
        && transTextArea.text !== (editorBackend.selectedEntry.translated_text || "")

    function flushPendingEdit() {
        if (editorBackend.selectedEntry && editorBackend.selectedEntry.id && typeof transTextArea !== "undefined" && transTextArea.text !== (editorBackend.selectedEntry.translated_text || "")) {
            editorBackend.updateSelectedTranslation(transTextArea.text)
        }
    }

    // Allow dragging and dropping game folder or Game.exe anywhere on Editor tab
    DropArea {
        id: dropArea
        anchors.fill: parent
        onDropped: (drop) => {
            if (drop.hasUrls && drop.urls.length > 0) {
                // Hand the raw URL to Python: QUrl.toLocalFile() handles
                // Windows (file:///D:/x) and POSIX (file:///home/x) correctly.
                editorBackend.setProjectPath(drop.urls[0].toString())
            }
        }
    }

    Connections {
        target: editorBackend
        function onSaveFinished(success, message) {
            if (typeof toast !== "undefined") {
                toast.show(success ? "success" : "error", success ? localeManager.strings.editor.save_success_title : localeManager.strings.editor.save_error_title, message)
            }
        }
        function onBatchReplaceFinished(count, message) {
            if (typeof toast !== "undefined") {
                toast.show(count > 0 ? "success" : "info", localeManager.strings.editor.batch_replace_toast_title, message)
            }
        }
        function onSelectedEntryChanged() {
            if (typeof transTextArea !== "undefined") {
                transTextArea.text = editorBackend.selectedEntry.translated_text || ""
            }
        }
        function onScanFinished(success, message, count) {
            if (!success && message) {
                if (typeof toast !== "undefined") {
                    toast.show("warning", localeManager.strings.editor.toast_title_generic, message)
                }
            }
        }
        function onAutoTranslateFinished(success, message) {
            if (typeof toast !== "undefined") {
                toast.show(
                    success ? "success" : "error",
                    localeManager.strings.editor.auto_translate_toast_title,
                    message
                )
            }
        }
    }

    BatchReplaceDialog {
        id: replaceDialog
        themeObj: t
        onReplaceRequested: (search, replace, fileScope, matchCase) => {
            editorBackend.batchReplace(search, replace, fileScope, "all", matchCase)
        }
    }

    AutoTranslateDialog {
        id: autoTranslateDialog
        themeObj: t
        onStartRequested: (options) => {
            editorBackend.startAutoTranslateWithOptions(options)
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 18
        spacing: 12

        // =====================================================
        // HEADER & ACTION BAR
        // =====================================================
        RowLayout {
            Layout.fillWidth: true
            spacing: 12

            ColumnLayout {
                spacing: 2
                Text {
                    text: localeManager.strings.editor.header_title
                    font.pixelSize: 18
                    font.bold: true
                    color: t ? t.textPrimary : "#ffffff"
                }
                Text {
                    text: !editorBackend.projectPath
                        ? localeManager.strings.editor.status_no_project
                        : (editorBackend.isScanning
                            ? (editorBackend.scanProgressText ? (editorBackend.scanProgressText + " (" + editorBackend.scanProgressCurrent + "%)") : (localeManager.strings.editor.status_scanning + getAnimatedDots()))
                            : (editorBackend.isAutoTranslating
                                ? editorBackend.autoTranslateStatus
                                : (editorBackend.projectLoaded
                                    ? (editorBackend.totalProjectCount > 0
                                        ? I18n.format(localeManager.strings.editor.status_loaded, {count: editorBackend.totalCount, total: editorBackend.totalProjectCount, modified: editorBackend.modifiedCount})
                                        : localeManager.strings.editor.status_no_data)
                                    : localeManager.strings.editor.status_waiting)))
                    font.pixelSize: 12
                    color: (editorBackend.isScanning || editorBackend.isAutoTranslating) ? "#ffaa00" : (t ? t.textSecondary : "#9a9ab2")
                }
            }

            Item { Layout.fillWidth: true }

            // Rescan Button
            TactileButton {
                label: localeManager.strings.editor.rescan_button
                variant: "ghost"
                enabled_: !editorBackend.isScanning && !appBackend.isRunning && !editorBackend.isAutoTranslating && editorBackend.projectPath.length > 0
                onClicked: editorBackend.loadProject(true)
            }

            // Auto Translate All button
            TactileButton {
                label: editorBackend.isAutoTranslating
                    ? I18n.format(localeManager.strings.editor.auto_translate_cancel_button, {progress: editorBackend.autoTranslateProgress})
                    : (localeManager.strings.editor.auto_translate_all_button + (editorBackend.untranslatedCount > 0 ? " (" + editorBackend.untranslatedCount + ")" : ""))
                variant: editorBackend.isAutoTranslating ? "warning" : "accent"
                enabled_: editorBackend.projectLoaded && !editorBackend.isScanning && !appBackend.isRunning
                onClicked: {
                    if (editorBackend.isAutoTranslating) {
                        editorBackend.cancelAutoTranslate()
                    } else {
                        autoTranslateDialog.openDialog()
                    }
                }
            }

            // Batch Replace Button
            TactileButton {
                label: localeManager.strings.editor.batch_replace_button
                variant: "ghost"
                enabled_: editorBackend.projectLoaded && !editorBackend.isScanning && !editorBackend.isAutoTranslating && !appBackend.isRunning
                onClicked: replaceDialog.openWith(editorBackend.selectedFile)
            }

            // Save Changes Button
            TactileButton {
                label: editorBackend.modifiedCount > 0
                    ? I18n.format(localeManager.strings.editor.save_button_with_count, {count: editorBackend.modifiedCount})
                    : localeManager.strings.editor.save_button
                variant: editorBackend.modifiedCount > 0 ? "accent" : "ghost"
                enabled_: (editorBackend.hasUnsavedChanges || root.hasPendingEdit) && !editorBackend.isScanning && !editorBackend.isAutoTranslating && !appBackend.isRunning
                onClicked: {
                    root.flushPendingEdit()
                    editorBackend.saveChanges()
                }
            }
        }

        // Auto-translate progress bar (visible only while running)
        Rectangle {
            Layout.fillWidth: true
            height: editorBackend.isAutoTranslating ? 6 : 0
            Behavior on height { NumberAnimation { duration: 200 } }
            radius: 3
            color: t ? t.border1 : "#2e2e3e"
            clip: true
            visible: height > 0

            Rectangle {
                width: parent.width * (editorBackend.autoTranslateProgress / 100)
                height: parent.height
                radius: parent.radius
                color: "#ffaa00"
                Behavior on width { NumberAnimation { duration: 300 } }
            }
        }

        // =====================================================
        // ACTIVE GAME PROJECT BAR & SELECTOR
        // =====================================================
        AppCard {
            Layout.fillWidth: true
            implicitHeight: editorBackend.isScanning ? 76 : 56
            Behavior on implicitHeight { NumberAnimation { duration: 200 } }

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 14
                anchors.rightMargin: 12
                spacing: 12

                Rectangle {
                    width: 36; height: 36; radius: 8
                    color: editorBackend.isScanning 
                        ? Qt.rgba(255, 170, 0, 0.15)
                        : (editorBackend.projectLoaded ? Qt.rgba(124, 108, 248, 0.2) : Qt.rgba(255, 255, 255, 0.05))
                    border.color: editorBackend.isScanning
                        ? "#ffaa00"
                        : (editorBackend.projectLoaded ? Qt.rgba(124, 108, 248, 0.4) : (t ? t.border1 : "#2e2e3e"))
                    border.width: 1

                    Text {
                        id: gameIconText
                        anchors.centerIn: parent
                        text: editorBackend.isScanning ? "🔄" : (editorBackend.projectLoaded ? "🎮" : "📂")
                        font.pixelSize: 16

                        RotationAnimator on rotation {
                            running: editorBackend.isScanning
                            from: 0
                            to: 360
                            duration: 1000
                            loops: Animation.Infinite
                        }
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 2

                    RowLayout {
                        spacing: 8
                        Text {
                            text: editorBackend.projectName ? editorBackend.projectName : localeManager.strings.editor.no_game_folder_selected
                            font.pixelSize: 13
                            font.bold: true
                            color: t ? t.textPrimary : "#ffffff"
                            elide: Text.ElideRight
                        }

                        // Animated Status Badge with pulse
                        Rectangle {
                            id: statusBadge
                            height: 20
                            width: badgeText.implicitWidth + 14
                            radius: 10
                            color: editorBackend.isScanning
                                ? Qt.rgba(255, 170, 0, 0.18)
                                : (editorBackend.projectLoaded
                                    ? Qt.rgba(76, 175, 80, 0.15)
                                    : Qt.rgba(244, 67, 54, 0.15))
                            border.color: editorBackend.isScanning
                                ? "#ffaa00"
                                : (editorBackend.projectLoaded ? "#4caf50" : "#f44336")
                            border.width: 1
                            visible: editorBackend.projectPath.length > 0

                            SequentialAnimation on opacity {
                                running: editorBackend.isScanning
                                loops: Animation.Infinite
                                NumberAnimation { to: 0.45; duration: 600; easing.type: Easing.InOutQuad }
                                NumberAnimation { to: 1.0; duration: 600; easing.type: Easing.InOutQuad }
                            }

                            Text {
                                id: badgeText
                                anchors.centerIn: parent
                                text: editorBackend.isScanning
                                    ? (localeManager.strings.editor.scanning_badge + getAnimatedDots())
                                    : (editorBackend.projectLoaded
                                        ? I18n.format(localeManager.strings.editor.text_count_badge, {count: editorBackend.totalProjectCount})
                                        : localeManager.strings.editor.no_data_badge)
                                font.pixelSize: 10
                                font.bold: true
                                color: parent.border.color
                            }
                        }
                    }

                    Text {
                        text: editorBackend.projectPath
                            ? editorBackend.projectPath
                            : localeManager.strings.editor.drop_placeholder
                        font.pixelSize: 11
                        color: t ? t.textMuted : "#777790"
                        elide: Text.ElideMiddle
                        Layout.fillWidth: true
                    }

                    // Live Animated Progress Bar
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 2
                        visible: editorBackend.isScanning

                        RowLayout {
                            Layout.fillWidth: true
                            Text {
                                text: editorBackend.scanProgressText || localeManager.strings.editor.parsing_files
                                font.pixelSize: 10
                                font.bold: true
                                color: "#ffaa00"
                                elide: Text.ElideMiddle
                                Layout.fillWidth: true
                            }
                            Text {
                                text: editorBackend.scanProgressCurrent + "%"
                                font.pixelSize: 10
                                font.bold: true
                                color: "#ffaa00"
                            }
                        }

                        Rectangle {
                            Layout.fillWidth: true
                            height: 4
                            radius: 2
                            color: Qt.rgba(255, 255, 255, 0.08)
                            clip: true

                            Rectangle {
                                height: parent.height
                                radius: 2
                                width: Math.max(6, parent.width * (Math.max(editorBackend.scanProgressCurrent, 5) / 100))
                                color: "#ffaa00"
                                Behavior on width { NumberAnimation { duration: 200; easing.type: Easing.OutQuad } }

                                Rectangle {
                                    anchors.fill: parent
                                    color: Qt.rgba(255, 255, 255, 0.4)
                                    SequentialAnimation on opacity {
                                        loops: Animation.Infinite
                                        running: editorBackend.isScanning
                                        NumberAnimation { from: 0.1; to: 0.8; duration: 450 }
                                        NumberAnimation { from: 0.8; to: 0.1; duration: 450 }
                                    }
                                }
                            }
                        }
                    }
                }

                TactileButton {
                    label: localeManager.strings.editor.select_game_button
                    variant: "accent"
                    enabled_: !editorBackend.isScanning && !appBackend.isRunning
                    onClicked: editorBackend.selectGameFolder()
                }
            }
        }

        // =====================================================
        // TWO-TIER FILTER TOOLBAR
        // =====================================================
        AppCard {
            Layout.fillWidth: true
            implicitHeight: filterCol.implicitHeight + 16

            ColumnLayout {
                id: filterCol
                anchors { fill: parent; margins: 10 }
                spacing: 8

                // Tier 1: Category Chips
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 6

                    Repeater {
                        model: editorBackend.categories
                        delegate: Rectangle {
                            height: 28
                            implicitWidth: catLabel.implicitWidth + 20
                            radius: 14
                            property bool isSelected: editorBackend.selectedCategory === modelData.key

                            color: isSelected 
                                ? (t ? t.accent : "#7c6cf8") 
                                : (catMouse.containsMouse ? (t ? t.bgHover : "#32324a") : (t ? t.bg4 : "#2a2a3a"))
                            border.color: isSelected ? "transparent" : (t ? t.border1 : "#2e2e3e")
                            border.width: 1

                            Text {
                                id: catLabel
                                anchors.centerIn: parent
                                text: localeManager.strings.editor.category_labels[modelData.key] || modelData.label
                                font.pixelSize: 11
                                font.bold: isSelected
                                color: isSelected ? "#ffffff" : (t ? t.textSecondary : "#bbbbd0")
                            }

                            MouseArea {
                                id: catMouse
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: editorBackend.setSelectedCategory(modelData.key)
                            }
                        }
                    }
                }

                // Tier 2: Search Field, File Dropdown, and Status Filter Chips
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8

                    // Search input
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.minimumWidth: 200
                        height: 34
                        radius: 8
                        color: t ? t.bg2 : "#1a1a24"
                        border.color: searchInput.activeFocus ? (t ? t.accent : "#7c6cf8") : (t ? t.border1 : "#2e2e3e")

                        RowLayout {
                            anchors { fill: parent; leftMargin: 8; rightMargin: 8 }
                            spacing: 6

                            Text { text: "🔍"; font.pixelSize: 12; opacity: 0.6 }

                            TextInput {
                                id: searchInput
                                Layout.fillWidth: true
                                verticalAlignment: TextInput.AlignVCenter
                                color: t ? t.textPrimary : "#ffffff"
                                font.pixelSize: 12
                                selectByMouse: true
                                text: editorBackend.searchQuery
                                onTextChanged: searchDebounce.restart()

                                Text {
                                    text: localeManager.strings.editor.search_placeholder
                                    color: t ? t.textMuted : "#666677"
                                    font.pixelSize: 12
                                    visible: !searchInput.text && !searchInput.activeFocus
                                    anchors.verticalCenter: parent.verticalCenter
                                }
                            }

                            Text {
                                text: "✕"
                                font.pixelSize: 11
                                color: t ? t.textMuted : "#777790"
                                visible: searchInput.text.length > 0
                                MouseArea {
                                    anchors.fill: parent
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: {
                                        searchInput.text = ""
                                        editorBackend.setSearchQuery("")
                                    }
                                }
                            }
                        }

                        Timer {
                            id: searchDebounce
                            interval: 200
                            repeat: false
                            onTriggered: editorBackend.setSearchQuery(searchInput.text)
                        }
                    }

                    // File ComboBox
                    ComboBox {
                        id: fileCombo
                        implicitWidth: 170
                        height: 34
                        model: editorBackend.fileList.map((f, i) => i === 0 ? localeManager.strings.editor.all_files_label : f)

                        currentIndex: {
                            var idx = editorBackend.fileList.indexOf(editorBackend.selectedFile)
                            return idx >= 0 ? idx : 0
                        }
                        onActivated: (index) => {
                            var selected = editorBackend.fileList[index]
                            editorBackend.setSelectedFile(selected === "Tüm Dosyalar" ? "all" : selected)
                        }

                        background: Rectangle {
                            color: t ? t.bg4 : "#2a2a3a"
                            border.color: t ? t.border2 : "#3d3d55"
                            border.width: 1
                            radius: 8
                        }
                        contentItem: Text {
                            text: fileCombo.displayText
                            color: t ? t.textPrimary : "#ffffff"
                            font.pixelSize: 12
                            leftPadding: 8
                            verticalAlignment: Text.AlignVCenter
                            elide: Text.ElideRight
                        }
                    }

                    // Status Chips
                    RowLayout {
                        spacing: 4

                        Repeater {
                            model: [
                                { key: "all", label: localeManager.strings.common.all },
                                { key: "modified", label: localeManager.strings.editor.status_chip_modified + " (" + editorBackend.modifiedCount + ")" },
                                { key: "warnings", label: localeManager.strings.editor.status_chip_warnings + " (" + editorBackend.warningCount + ")" },
                                { key: "untranslated", label: localeManager.strings.editor.status_chip_untranslated + " (" + editorBackend.untranslatedCount + ")" }
                            ]
                            delegate: Rectangle {
                                height: 28
                                implicitWidth: statusLabel.implicitWidth + 14
                                radius: 6
                                property bool isSelected: editorBackend.selectedStatus === modelData.key

                                color: isSelected 
                                    ? (t ? t.accentGlow : "#3a346e") 
                                    : (statusMouse.containsMouse ? (t ? t.bgHover : "#32324a") : (t ? t.bg4 : "#2a2a3a"))
                                border.color: isSelected ? (t ? t.accent : "#7c6cf8") : (t ? t.border1 : "#2e2e3e")
                                border.width: 1

                                Text {
                                    id: statusLabel
                                    anchors.centerIn: parent
                                    text: modelData.label
                                    font.pixelSize: 11
                                    color: isSelected ? (t ? t.accentLight : "#c4b5fd") : (t ? t.textSecondary : "#bbbbd0")
                                }

                                MouseArea {
                                    id: statusMouse
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: editorBackend.setSelectedStatus(modelData.key)
                                }
                            }
                        }
                    }
                }
            }
        }

        // =====================================================
        // MASTER: VIRTUALIZED STRING LIST (SPLIT TOP AREA)
        // =====================================================
        AppCard {
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true

            ColumnLayout {
                anchors.fill: parent
                spacing: 0

                // Table Header
                Rectangle {
                    Layout.fillWidth: true
                    height: 32
                    color: t ? t.bg4 : "#2a2a3a"

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 12
                        anchors.rightMargin: 12
                        spacing: 8

                        Text { width: 24; text: "●"; font.pixelSize: 11; color: t ? t.textMuted : "#666677" }
                        Text { width: 120; text: localeManager.strings.editor.col_file; font.pixelSize: 11; font.bold: true; color: t ? t.textSecondary : "#bbbbd0"; elide: Text.ElideRight }
                        Text { width: 90;  text: localeManager.strings.editor.col_category; font.pixelSize: 11; font.bold: true; color: t ? t.textSecondary : "#bbbbd0"; elide: Text.ElideRight }
                        Text { Layout.fillWidth: true; text: localeManager.strings.editor.col_original; font.pixelSize: 11; font.bold: true; color: t ? t.textSecondary : "#bbbbd0"; elide: Text.ElideRight }
                        Text { Layout.fillWidth: true; text: localeManager.strings.editor.col_translation; font.pixelSize: 11; font.bold: true; color: t ? t.textSecondary : "#bbbbd0"; elide: Text.ElideRight }
                    }
                }

                // Table Content List
                ListView {
                    id: stringListView
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    model: editorBackend.tableModel
                    clip: true

                    ScrollBar.vertical: ScrollBar {
                        policy: ScrollBar.AsNeeded
                    }

                    // Informative Empty State Container
                    ColumnLayout {
                        anchors.centerIn: parent
                        spacing: 12
                        visible: editorBackend.totalCount === 0 || !editorBackend.projectLoaded
                        width: Math.min(parent.width - 40, 480)

                        Text {
                            Layout.alignment: Qt.AlignHCenter
                            text: !editorBackend.projectPath
                                ? "📂"
                                : (!editorBackend.projectLoaded
                                    ? "⚠️"
                                    : (editorBackend.totalProjectCount === 0 ? "⚠️" : "🔍"))
                            font.pixelSize: 36
                        }

                        Text {
                            Layout.alignment: Qt.AlignHCenter
                            Layout.fillWidth: true
                            horizontalAlignment: Text.AlignHCenter
                            wrapMode: Text.Wrap
                            font.bold: true
                            font.pixelSize: 15
                            color: t ? t.textPrimary : "#ffffff"
                            text: !editorBackend.projectPath
                                ? localeManager.strings.editor.empty_no_folder_title
                                : (!editorBackend.projectLoaded || editorBackend.totalProjectCount === 0
                                    ? localeManager.strings.editor.empty_no_data_title
                                    : localeManager.strings.editor.empty_no_match_title)
                        }

                        Text {
                            Layout.alignment: Qt.AlignHCenter
                            Layout.fillWidth: true
                            horizontalAlignment: Text.AlignHCenter
                            wrapMode: Text.Wrap
                            font.pixelSize: 12
                            color: t ? t.textMuted : "#777790"
                            text: !editorBackend.projectPath
                                ? localeManager.strings.editor.empty_no_folder_desc
                                : (!editorBackend.projectLoaded || editorBackend.totalProjectCount === 0
                                    ? I18n.format(localeManager.strings.editor.empty_no_data_desc, {path: editorBackend.projectPath})
                                    : localeManager.strings.editor.empty_no_match_desc)
                        }

                        Item { height: 4 }

                        TactileButton {
                            Layout.alignment: Qt.AlignHCenter
                            label: (!editorBackend.projectLoaded || editorBackend.totalProjectCount === 0)
                                ? localeManager.strings.editor.select_game_folder_button
                                : localeManager.strings.editor.clear_filters_button
                            variant: "accent"
                            onClicked: {
                                if (!editorBackend.projectLoaded || editorBackend.totalProjectCount === 0) {
                                    editorBackend.selectGameFolder()
                                } else {
                                    if (typeof searchInput !== "undefined") {
                                        searchInput.text = ""
                                    }
                                    editorBackend.setSearchQuery("")
                                    editorBackend.setSelectedCategory("all")
                                    editorBackend.setSelectedFile("all")
                                    editorBackend.setSelectedStatus("all")
                                }
                            }
                        }
                    }

                    delegate: Rectangle {
                        id: rowDelegate
                        width: stringListView.width
                        height: 38
                        property bool isSelected: editorBackend.selectedEntry.id === model.entryId

                        color: isSelected 
                            ? (t ? t.accentGlow : "#38326b") 
                            : (rowMouse.containsMouse ? (t ? t.bgHover : "#28283a") : "transparent")

                        Rectangle {
                            width: parent.width; height: 1
                            color: t ? t.border1 : "#2e2e3e"
                            anchors.bottom: parent.bottom
                        }

                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 12
                            anchors.rightMargin: 12
                            spacing: 8

                            // Status Dot
                            Rectangle {
                                width: 8; height: 8; radius: 4
                                color: {
                                    if (model.hasWarning) return "#f59e0b" // warning orange
                                    if (model.isModified) return "#38bdf8" // modified cyan
                                    if (model.translatedText && model.translatedText !== model.originalText) return "#10b981" // translated green
                                    return "#6b7280" // untranslated grey
                                }
                            }

                            // File Name
                            Text {
                                width: 120
                                text: model.fileName
                                font.pixelSize: 11
                                color: t ? t.textSecondary : "#bbbbd0"
                                elide: Text.ElideMiddle
                            }

                            // Category Badge
                            Rectangle {
                                width: 80; height: 20; radius: 4
                                color: t ? t.bg4 : "#2a2a3a"
                                Text {
                                    anchors.centerIn: parent
                                    text: (localeManager.strings.editor.category_labels && localeManager.strings.editor.category_labels[model.category]) || model.categoryLabel
                                    font.pixelSize: 10
                                    color: t ? t.textMuted : "#888899"
                                    elide: Text.ElideRight
                                }
                            }

                            // Original Text Preview
                            Text {
                                Layout.fillWidth: true
                                text: model.originalText.replace(/\n/g, " ↵ ")
                                font.pixelSize: 12
                                color: t ? t.textPrimary : "#ffffff"
                                elide: Text.ElideRight
                            }

                            // Translated Text Preview
                            Text {
                                Layout.fillWidth: true
                                text: model.translatedText.replace(/\n/g, " ↵ ")
                                font.pixelSize: 12
                                color: model.isModified 
                                    ? (t ? t.accentLight : "#c4b5fd") 
                                    : (t ? t.textSecondary : "#bbbbd0")
                                font.bold: model.isModified
                                elide: Text.ElideRight
                            }
                        }

                        MouseArea {
                            id: rowMouse
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: root.selectRow(model.entryId)
                        }
                    }
                }

                // =====================================================
                // PAGINATION CONTROLLER
                // =====================================================
                Rectangle {
                    Layout.fillWidth: true
                    height: 38
                    color: t ? t.bg4 : "#252535"
                    border.color: t ? t.border1 : "#2e2e3e"
                    border.width: 1

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 12
                        anchors.rightMargin: 12
                        spacing: 8

                        Text {
                            text: I18n.format(localeManager.strings.editor.pagination_label, {count: editorBackend.totalCount, page: editorBackend.currentPage, total: editorBackend.totalPages})
                            font.pixelSize: 11
                            color: t ? t.textMuted : "#888899"
                        }

                        Item { Layout.fillWidth: true }

                        // First Page
                        TactileButton {
                            label: "⏮"
                            variant: "ghost"
                            implicitHeight: 28
                            implicitWidth: 32
                            enabled_: editorBackend.currentPage > 1
                            onClicked: root.changePage(1)
                        }

                        // Prev Page
                        TactileButton {
                            label: "◀"
                            variant: "ghost"
                            implicitHeight: 28
                            implicitWidth: 32
                            enabled_: editorBackend.currentPage > 1
                            onClicked: root.changePage(editorBackend.currentPage - 1)
                        }

                        Text {
                            text: editorBackend.currentPage
                            font.pixelSize: 12
                            font.bold: true
                            color: t ? t.accent : "#7c6cf8"
                            leftPadding: 6; rightPadding: 6
                        }

                        // Next Page
                        TactileButton {
                            label: "▶"
                            variant: "ghost"
                            implicitHeight: 28
                            implicitWidth: 32
                            enabled_: editorBackend.currentPage < editorBackend.totalPages
                            onClicked: root.changePage(editorBackend.currentPage + 1)
                        }

                        // Last Page
                        TactileButton {
                            label: "⏭"
                            variant: "ghost"
                            implicitHeight: 28
                            implicitWidth: 32
                            enabled_: editorBackend.currentPage < editorBackend.totalPages
                            onClicked: root.changePage(editorBackend.totalPages)
                        }

                        // Page Size
                        ComboBox {
                            implicitWidth: 90
                            height: 28
                            model: localeManager.strings.editor.page_size_options
                            currentIndex: editorBackend.pageSize === 50 ? 0 : (editorBackend.pageSize === 100 ? 1 : 2)
                            onActivated: (idx) => {
                                var sizes = [50, 100, 200]
                                editorBackend.setPageSize(sizes[idx])
                            }
                            background: Rectangle {
                                color: t ? t.bg3 : "#22222f"
                                border.color: t ? t.border1 : "#2e2e3e"
                                radius: 6
                            }
                            contentItem: Text {
                                text: parent.displayText
                                color: t ? t.textPrimary : "#ffffff"
                                font.pixelSize: 11
                                leftPadding: 6
                                verticalAlignment: Text.AlignVCenter
                            }
                        }
                    }
                }
            }
        }

        // =====================================================
        // DETAIL: MULTI-LINE EDITING DRAWER (BOTTOM SECTION)
        // =====================================================
        AppCard {
            id: detailCard
            Layout.fillWidth: true
            height: 235
            visible: editorBackend.selectedEntry.id !== undefined && editorBackend.selectedEntry.id > 0
            property int liveLineCount: (typeof transTextArea !== "undefined" && transTextArea.text) ? ((transTextArea.text.match(/\n/g) || []).length + 1) : 1

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 12
                spacing: 6

                // Detail Top Info Row
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8

                    Text {
                        text: (editorBackend.selectedEntry.file_name || "") + " ➔ " + (editorBackend.selectedEntry.json_path || "")
                        font.pixelSize: 11
                        font.bold: true
                        color: t ? t.textSecondary : "#bbbbd0"
                    }

                    Item { Layout.fillWidth: true }

                    // Line Counter
                    Rectangle {
                        height: 20
                        implicitWidth: lineCountText.implicitWidth + 12
                        radius: 4
                        color: (detailCard.liveLineCount > 4) ? "#ef4444" : (t ? t.bg4 : "#2a2a3a")
                        Text {
                            id: lineCountText
                            anchors.centerIn: parent
                            text: I18n.format(localeManager.strings.editor.line_counter, {count: detailCard.liveLineCount})
                            font.pixelSize: 10
                            font.bold: true
                            color: (detailCard.liveLineCount > 4) ? "#ffffff" : (t ? t.textMuted : "#888899")
                        }
                    }

                    // Warning Badge
                    Rectangle {
                        height: 20
                        implicitWidth: warnText.implicitWidth + 12
                        radius: 4
                        color: "#f59e0b"
                        visible: Boolean(editorBackend.selectedEntry.has_warning)
                        Text {
                            id: warnText
                            anchors.centerIn: parent
                            text: "⚠️ " + (editorBackend.selectedEntry.warning_msg || localeManager.strings.editor.escape_code_warning_fallback)
                            font.pixelSize: 10
                            font.bold: true
                            color: "#ffffff"
                        }
                    }
                }

                // Pre-Context (Previous line if dialogue sequence)
                Text {
                    text: localeManager.strings.editor.prev_context_prefix + (editorBackend.selectedEntry.prev_context || "").replace(/\n/g, " ")
                    font.pixelSize: 11
                    font.italic: true
                    color: t ? t.textMuted : "#666677"
                    visible: Boolean(editorBackend.selectedEntry.prev_context)
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                }

                // Clickable Code Chips (Full width above dual editor panes)
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 6
                    visible: (editorBackend.selectedEntry.escape_codes || []).length > 0

                    Text {
                        text: localeManager.strings.editor.add_code_label
                        font.pixelSize: 10
                        color: t ? t.textMuted : "#666677"
                    }

                    Flow {
                        Layout.fillWidth: true
                        spacing: 4

                        Repeater {
                            model: editorBackend.selectedEntry.escape_codes || []
                            delegate: Rectangle {
                                height: 18
                                implicitWidth: chipText.implicitWidth + 8
                                radius: 3
                                color: t ? t.bg4 : "#2a2a3a"
                                border.color: t ? t.accent : "#7c6cf8"
                                border.width: 1

                                Text {
                                    id: chipText
                                    anchors.centerIn: parent
                                    text: modelData
                                    font.pixelSize: 9
                                    font.bold: true
                                    color: t ? t.accentLight : "#c4b5fd"
                                }
                                MouseArea {
                                    anchors.fill: parent
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: {
                                        var pos = transTextArea.cursorPosition
                                        transTextArea.insert(pos, modelData)
                                        transTextArea.forceActiveFocus()
                                    }
                                }
                            }
                        }
                    }
                }

                // Dual Editor Panes (Original vs Translated)
                RowLayout {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    spacing: 12

                    // Original Pane (Read-Only)
                    ColumnLayout {
                        Layout.fillWidth: true
                        Layout.preferredWidth: 1
                        Layout.fillHeight: true
                        spacing: 4

                        // Original Text Display
                        Rectangle {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            color: t ? t.bg2 : "#1a1a24"
                            border.color: t ? t.border1 : "#2e2e3e"
                            radius: 8

                            ScrollView {
                                anchors.fill: parent
                                anchors.margins: 6
                                TextArea {
                                    text: editorBackend.selectedEntry.original_text || ""
                                    readOnly: true
                                    wrapMode: Text.Wrap
                                    color: t ? t.textSecondary : "#bbbbd0"
                                    font.pixelSize: 12
                                    selectByMouse: true
                                }
                            }
                        }
                    }

                    // Translated Pane (Editable)
                    ColumnLayout {
                        Layout.fillWidth: true
                        Layout.preferredWidth: 1
                        Layout.fillHeight: true
                        spacing: 4

                        Rectangle {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            color: t ? t.bg2 : "#1a1a24"
                            border.color: transTextArea.activeFocus ? (t ? t.accent : "#7c6cf8") : (t ? t.border1 : "#2e2e3e")
                            radius: 8

                            ScrollView {
                                anchors.fill: parent
                                anchors.margins: 6
                                TextArea {
                                    id: transTextArea
                                    text: editorBackend.selectedEntry.translated_text || ""
                                    wrapMode: Text.Wrap
                                    color: t ? t.textPrimary : "#ffffff"
                                    font.pixelSize: 12
                                    selectByMouse: true

                                    Keys.onPressed: (event) => {
                                        if (event.key === Qt.Key_Return && (event.modifiers & Qt.ControlModifier)) {
                                            editorBackend.updateSelectedTranslation(transTextArea.text)
                                            event.accepted = true
                                        }
                                    }
                                }
                            }
                        }
                    }
                }

                // Next Context (Succeeding line if dialogue sequence)
                Text {
                    text: localeManager.strings.editor.next_context_prefix + (editorBackend.selectedEntry.next_context || "").replace(/\n/g, " ")
                    font.pixelSize: 11
                    font.italic: true
                    color: t ? t.textMuted : "#666677"
                    visible: Boolean(editorBackend.selectedEntry.next_context)
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                }

                // Detail Bottom Action Buttons
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8

                    Text {
                        text: localeManager.strings.editor.ctrl_enter_tip
                        font.pixelSize: 10
                        color: t ? t.textMuted : "#666677"
                    }

                    Item { Layout.fillWidth: true }

                    // Revert Entry Button
                    TactileButton {
                        label: localeManager.strings.editor.revert_button
                        variant: "ghost"
                        implicitHeight: 26
                        onClicked: {
                            editorBackend.revertSelectedEntry()
                            transTextArea.text = editorBackend.selectedEntry.translated_text || ""
                        }
                    }

                    // Apply Translation Button
                    TactileButton {
                        label: localeManager.strings.editor.apply_button
                        variant: "accent"
                        implicitHeight: 26
                        onClicked: editorBackend.updateSelectedTranslation(transTextArea.text)
                    }
                }
            }
        }
    }
}
