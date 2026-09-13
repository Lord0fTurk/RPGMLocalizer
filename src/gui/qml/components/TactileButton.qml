import QtQuick 2.15
import QtQuick.Controls 2.15

Rectangle {
    id: root
    property var themeObj: null
    property string label: "Button"
    property string variant: "accent" // "accent", "ghost", "danger"
    property bool enabled_: true

    signal clicked()

    implicitHeight: 38
    implicitWidth: btnText.implicitWidth + 32
    radius: 9
    scale: btnMouse.pressed ? 0.97 : 1.0
    opacity: root.enabled_ ? 1.0 : 0.45

    Behavior on scale {
        NumberAnimation { duration: 90; easing.type: Easing.OutQuad }
    }

    Behavior on opacity {
        NumberAnimation { duration: 150 }
    }

    gradient: root.variant === "accent" ? accentGrad : null
    color: {
        if (root.variant === "accent") return "transparent"
        if (root.variant === "danger") return btnMouse.pressed ? "#dc2626" : "#ef4444"
        // ghost variant
        if (btnMouse.pressed) return root.themeObj ? root.themeObj.bg4 : "#2a2a3a"
        if (btnMouse.containsMouse) return root.themeObj ? root.themeObj.bgHover : "#32324a"
        return "transparent"
    }

    border.width: root.variant === "ghost" ? 1 : 0
    border.color: root.themeObj ? root.themeObj.border2 : "#3d3d55"

    Gradient {
        id: accentGrad
        orientation: Gradient.Horizontal
        GradientStop { position: 0.0; color: root.themeObj ? root.themeObj.accentDark : "#5a4dd4" }
        GradientStop { position: 1.0; color: root.themeObj ? root.themeObj.accent : "#7c6cf8" }
    }

    // Hover glow highlight
    Rectangle {
        anchors.fill: parent
        radius: parent.radius
        color: btnMouse.containsMouse ? Qt.rgba(255, 255, 255, 0.08) : "transparent"
        Behavior on color { ColorAnimation { duration: 120 } }
    }

    Text {
        id: btnText
        anchors.centerIn: parent
        text: root.label
        font.pixelSize: 13
        font.bold: true
        color: root.variant === "ghost" ? (root.themeObj ? root.themeObj.textSecondary : "#9090b8") : "white"
    }

    MouseArea {
        id: btnMouse
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: root.enabled_ ? Qt.PointingHandCursor : Qt.ArrowCursor
        enabled: root.enabled_
        onClicked: root.clicked()
    }
}
