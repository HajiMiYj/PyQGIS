"""QgsLabelPropertyDialog using the original 3.34 Designer form and widget names."""
from pathlib import Path
from qgis.PyQt import uic
from qgis.PyQt.QtCore import QCoreApplication, Qt, pyqtSignal, QUrl
from qgis.PyQt.QtGui import QColor, QFont, QFontDatabase, QDesktopServices
from qgis.PyQt.QtWidgets import QDialog, QDialogButtonBox, QMenu
from qgis.core import QgsPalLayerSettings as Pal
from qgis.gui import QgsGui
from .qgsmaptoollabel import isNull


class QgsLabelPropertyDialog(QDialog):
    applied = pyqtSignal()
    # The same properties and controls as QgsLabelPropertyDialog::init().
    CONTROLS = {
        Pal.Show: ('mShowLabelChkbx', 'bool'), Pal.AlwaysShow: ('mAlwaysShowChkbx', 'bool'),
        Pal.CalloutDraw: ('mShowCalloutChkbx', 'bool'), Pal.BufferDraw: ('mBufferDrawChkbx', 'bool'),
        Pal.Bold: ('mFontBoldBtn', 'bool'), Pal.Italic: ('mFontItalicBtn', 'bool'),
        Pal.Underline: ('mFontUnderlineBtn', 'bool'), Pal.Strikeout: ('mFontStrikethroughBtn', 'bool'),
        Pal.LabelAllParts: ('mLabelAllPartsCheckBox', 'bool'),
        Pal.Size: ('mFontSizeSpinBox', 'number'), Pal.BufferSize: ('mBufferSizeSpinBox', 'number'),
        Pal.LabelDistance: ('mLabelDistanceSpinBox', 'number'), Pal.PositionX: ('mXCoordSpinBox', 'number'),
        Pal.PositionY: ('mYCoordSpinBox', 'number'), Pal.LabelRotation: ('mRotationSpinBox', 'number'),
        Pal.Color: ('mFontColorButton', 'color'), Pal.BufferColor: ('mBufferColorButton', 'color'),
        Pal.MultiLineAlignment: ('mMultiLineAlignComboBox', 'combo'),
        Pal.Hali: ('mHaliComboBox', 'combo'), Pal.Vali: ('mValiComboBox', 'combo'),
        Pal.Family: ('mFontFamilyCmbBx', 'font'), Pal.FontStyle: ('mFontStyleCmbBx', 'style'),
        Pal.MinScale: ('mMinScaleWidget', 'scale'), Pal.MaxScale: ('mMaxScaleWidget', 'scale'),
    }

    def __init__(self, details, tool, parent=None):
        super().__init__(parent or tool.canvas())
        uic.loadUi(str(Path(__file__).resolve().parents[2] / 'ui/labeling/qgslabelpropertydialogbase.ui'), self)
        self.setObjectName('QgsLabelPropertyDialog')
        QgsGui.enableAutoGeometryRestore(self)
        self.mDetails, self.mTool = details, tool
        self.mChangedProperties = {}
        self.mIndexes = {p: tool.dataDefinedColumnIndex(p, details) for p in self.CONTROLS}
        settings = details.settings
        fmt, font = settings.format(), details.pos.labelFont
        buffer = fmt.buffer()
        defaults = {
            Pal.Show: True, Pal.AlwaysShow: False, Pal.CalloutDraw: bool(settings.callout() and settings.callout().enabled()),
            Pal.BufferDraw: buffer.enabled(), Pal.Bold: font.bold(), Pal.Italic: font.italic(),
            Pal.Underline: font.underline(), Pal.Strikeout: font.strikeOut(), Pal.LabelAllParts: settings.labelPerPart,
            Pal.Size: fmt.size(), Pal.BufferSize: buffer.size(), Pal.LabelDistance: settings.dist,
            Pal.PositionX: None, Pal.PositionY: None, Pal.LabelRotation: 0,
            Pal.Color: fmt.color(), Pal.BufferColor: buffer.color(),
            Pal.Hali: 'Left', Pal.Vali: 'Bottom', Pal.MultiLineAlignment: '',
            Pal.Family: font.family(), Pal.FontStyle: QFontDatabase().styleString(font),
            Pal.MinScale: settings.minimumScale, Pal.MaxScale: settings.maximumScale,
        }
        for name, values in [
            ('mMultiLineAlignComboBox', [('图层默认', ''), ('左', 'Left'), ('居中', 'Center'), ('右', 'Right'), ('两端对齐', 'Justify'), ('跟随标注位置', 'Follow')]),
            ('mHaliComboBox', [('左', 'Left'), ('居中', 'Center'), ('右', 'Right')]),
            ('mValiComboBox', [('底部', 'Bottom'), ('基线', 'Base'), ('一半', 'Half'), ('大写字母高度', 'Cap'), ('顶部', 'Top')]),
        ]:
            widget = getattr(self, name)
            for label, value in values: widget.addItem(label, value)
        for prop, (name, kind) in self.CONTROLS.items():
            widget = getattr(self, name)
            widget.setEnabled(self.mIndexes[prop] >= 0)
            value = tool.value(details, prop, defaults[prop])
            if kind == 'number':
                widget.setClearValue(widget.minimum())
                widget.setSpecialValueText('图层默认')
                widget.setValue(float(value) if value is not None else widget.minimum())
                widget.valueChanged.connect(lambda value, p=prop, w=widget: self.insertChangedValue(p, None if value == w.minimum() else value))
            elif kind == 'bool':
                widget.setChecked(bool(value))
                widget.toggled.connect(lambda value, p=prop: self.insertChangedValue(p, int(value)))
            elif kind == 'color':
                widget.setAllowOpacity(True)
                widget.setColor(QColor(value))
                widget.colorChanged.connect(lambda value, p=prop: self.insertChangedValue(p, value.name(QColor.HexArgb)))
            elif kind == 'combo':
                index = widget.findData(str(value), Qt.UserRole, Qt.MatchFixedString)
                widget.setCurrentIndex(max(index, 0))
                widget.currentIndexChanged.connect(lambda index, p=prop, w=widget: self.insertChangedValue(p, w.itemData(index) or None))
            elif kind == 'font':
                widget.setCurrentFont(QFont(str(value)))
                widget.currentFontChanged.connect(self.fontFamilyChanged)
            elif kind == 'style':
                widget.addItems(QFontDatabase().styles(font.family()))
                widget.setCurrentText(str(value))
                widget.currentTextChanged.connect(self.fontStyleChanged)
            elif kind == 'scale':
                widget.setMapCanvas(tool.canvas())
                widget.setShowCurrentScaleButton(True)
                widget.setScale(float(value or 0))
                widget.scaleChanged.connect(lambda value, p=prop: self.scaleChanged(p, value))
            widget.setContextMenuPolicy(Qt.CustomContextMenu)
            widget.customContextMenuRequested.connect(lambda point, p=prop, w=widget: self.resetMenu(p, w, point))
        self.mRotationSpinBox.setClearValue(0)
        feature = details.layer.getFeature(details.pos.featureId)
        self.mCurLabelField = -1 if settings.isExpression else details.layer.fields().lookupField(settings.fieldName)
        self.mLabelTextLineEdit.setText(details.pos.labelText if self.mCurLabelField < 0 else str(feature[self.mCurLabelField]))
        self.mLabelTextLineEdit.setEnabled(self.mCurLabelField >= 0)
        if settings.isExpression: self.mLabelTextLabel.setText(QCoreApplication.translate('QgsLabelPropertyDialog', 'Expression result'))
        self.mLabelTextLineEdit.textChanged.connect(self.labelTextChanged)
        self.buttonBox.button(QDialogButtonBox.Apply).clicked.connect(self.applied)
        self.buttonBox.helpRequested.connect(lambda: QDesktopServices.openUrl(QUrl('https://docs.qgis.org/3.34/en/docs/user_manual/working_with_vector/vector_properties.html#label-toolbar')))

    def insertChangedValue(self, prop, value):
        index = self.mIndexes.get(prop, -1)
        if index >= 0: self.mChangedProperties[index] = value

    def labelTextChanged(self, text):
        if self.mCurLabelField >= 0: self.mChangedProperties[self.mCurLabelField] = text

    def fontFamilyChanged(self, font):
        self.insertChangedValue(Pal.Family, font.family())
        old = self.mFontStyleCmbBx.currentText()
        self.mFontStyleCmbBx.blockSignals(True)
        self.mFontStyleCmbBx.clear()
        self.mFontStyleCmbBx.addItems(QFontDatabase().styles(font.family()))
        self.mFontStyleCmbBx.setCurrentText(old)
        self.mFontStyleCmbBx.blockSignals(False)
        self.fontStyleChanged(self.mFontStyleCmbBx.currentText())

    def fontStyleChanged(self, style):
        self.insertChangedValue(Pal.FontStyle, style)
        font = QFontDatabase().font(self.mFontFamilyCmbBx.currentFont().family(), style, 12)
        self.mFontBoldBtn.setChecked(font.bold())
        self.mFontItalicBtn.setChecked(font.italic())

    def scaleChanged(self, prop, scale):
        self.insertChangedValue(prop, scale if scale else None)
        index = self.mTool.dataDefinedColumnIndex(Pal.ScaleVisibility, self.mDetails)
        if index >= 0: self.mChangedProperties[index] = int(bool(self.mMinScaleWidget.scale() or self.mMaxScaleWidget.scale()))

    def resetMenu(self, prop, widget, point):
        menu = QMenu(self)
        action = menu.addAction('清除此要素的覆盖值，使用图层默认')
        if menu.exec_(widget.mapToGlobal(point)) == action:
            self.insertChangedValue(prop, None)
            widget.setToolTip('将清除覆盖值；点击应用或确定后生效')

    def changedProperties(self): return dict(self.mChangedProperties)
    def clearChanges(self): self.mChangedProperties.clear()
