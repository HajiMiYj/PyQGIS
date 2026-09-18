"""Counterpart of options/qgscodeeditoroptions.cpp, using its original form.

The page was missing from the port. Native keeps the preview in sync through
QgsCodeEditor::setCustomAppearance(), which is not exported to PyQGIS, but
QgsCodeEditor::color()/defaultColor() read the settings on demand, so the same
result is reached by writing the settings and rebuilding the preview editors.
"""
from pathlib import Path
from qgis.PyQt import uic
from qgis.PyQt.QtGui import QFont
from qgis.core import QgsApplication, QgsSettings, Qgis
from qgis.gui import (QgsOptionsPageWidget, QgsCodeEditor, QgsCodeEditorColorScheme,
                      QgsCodeEditorShell, QgsCodeEditorPython, QgsCodeEditorExpression,
                      QgsCodeEditorSQL, QgsCodeEditorHTML, QgsCodeEditorCSS,
                      QgsCodeEditorJavascript, QgsCodeEditorR, QgsGui)

ROOT = Path(__file__).resolve().parents[2]
# QgsSettings::Section::Gui prefixes these keys with "gui/".
OVERRIDE_COLORS = 'gui/codeEditor/overrideColors'
COLOR_SCHEME = 'gui/codeEditor/colorScheme'
FONT_FAMILY = 'gui/codeEditor/fontfamily'
FONT_SIZE = 'gui/codeEditor/fontsize'
SPLITTER_STATE = 'Windows/CodeEditorOptions/splitterState'

# (ColorRole name, widget name), in the order native wires them.
COLOR_ROLES = (
    ('Default', 'mColorDefault'), ('Keyword', 'mColorKeyword'), ('Class', 'mColorClass'),
    ('Method', 'mColorFunction'), ('Decoration', 'mColorDecorator'), ('Number', 'mColorNumber'),
    ('Comment', 'mColorComment'), ('CommentLine', 'mColorCommentLine'),
    ('CommentBlock', 'mColorCommentBlock'), ('Background', 'mColorBackground'),
    ('Cursor', 'mColorCursor'), ('CaretLine', 'mColorCaretLine'), ('Operator', 'mColorOperator'),
    ('QuotedOperator', 'mColorQuotedOperator'), ('Identifier', 'mColorIdentifier'),
    ('QuotedIdentifier', 'mColorQuotedIdentifier'), ('Tag', 'mColorTag'),
    ('UnknownTag', 'mColorUnknownTag'), ('SingleQuote', 'mColorSingleQuote'),
    ('DoubleQuote', 'mColorDoubleQuote'), ('TripleSingleQuote', 'mColorTripleSingleQuote'),
    ('TripleDoubleQuote', 'mColorTripleDoubleQuote'), ('MarginBackground', 'mColorMarginBackground'),
    ('MarginForeground', 'mColorMarginForeground'),
    ('SelectionBackground', 'mColorSelectionBackground'),
    ('SelectionForeground', 'mColorSelectionForeground'),
    ('MatchedBraceBackground', 'mColorBraceBackground'),
    ('MatchedBraceForeground', 'mColorBraceForeground'), ('Edge', 'mColorEdge'),
    ('Fold', 'mColorFold'), ('Error', 'mColorError'), ('ErrorBackground', 'mColorErrorBackground'),
    ('FoldIconForeground', 'mColorFoldIcon'), ('FoldIconHalo', 'mColorFoldIconHalo'),
    ('IndentationGuide', 'mColorIndentation'),
)

PYTHON_SAMPLE = '''def simple_function(x,y,z):
    """
    Function docstring
    """
    return [1, 1.2, "val", 'a string', {'a': True, 'b': False}]

@my_decorator
def somefunc(param1: str='', param2=0):
    \'\'\'A docstring\'\'\'
    if param1 > param2: # interesting
        print('Gre\\'ater'.lower())
    return (param2 - param1 + 1 + 0b10) or None

class SomeClass:
    """
    My class docstring
    """
    pass
'''

EXPRESSION_SAMPLE = '''aggregate(layer:='rail_stations',
    aggregate:='collect', -- a comment
    expression:=centroid($geometry), /* a comment */
    filter:="region_name" = attribute(@parent,'name') + 55
)
'''

SQL_SAMPLE = '''CREATE TABLE "my_table" (
    "pk" serial NOT NULL PRIMARY KEY,
    "a_field" integer,
    "another_field" varchar(255)
);

-- Retrieve values
SELECT count(*) FROM "my_table" WHERE "a_field" > 'a value';
'''

HTML_SAMPLE = '''<html>
  <head>
    <title>QGIS</title>
  </head>
  <body>
    <h1>QGIS Rocks!</h1>
    <img src="qgis.png" style="width: 100px" />
    <!--Sample comment-->
    <p>Sample paragraph</p>
  </body>
</html>
'''

CSS_SAMPLE = '''@import url(print.css);

@font-face {
 font-family: DroidSans; /* A comment */
 src: url('DroidSans.ttf');
}

p.style_name:lang(en) {
 color: #F0F0F0;
 background: #600;
}

ul > li, a:hover {
 line-height: 11px;
 text-decoration: underline;
}

@media print {
  a[href^=http]::after {
    content: attr(href)
  }
}
'''

JS_SAMPLE = '''// my sample JavaScript function

window.onAction(function update() {
    /* Do some work */
    var prevPos = closure.pos;

    element.width = 100;
    element.height = 2500;
    element.name = 'a string';
    element.title= "another string";

    if (prevPos.x > 100) {
        element.x += max(100*2, 100);
    }
});
'''

R_SAMPLE = '''# a comment
x <- 1:12
sample(x)
sample(x, replace = TRUE)

resample <- function(x, ...) x[sample.int(length(x), ...)]
resample(x[x >  8]) # length 2

a_variable <- "My string"

`%func_name%` <- function(arg_1,arg_2) {
  # function body
}

`%pwr%` <- function(x,y)
{
 return(x^y)
}
'''

BASH_SAMPLE = '''#!/bin/bash

# This script takes two arguments: a directory and a file extension.
# It finds all the files in the directory that have the given extension
# and prints out their names and sizes.

[ $# -ne 2 ] && { echo "Usage: $0 <directory> <file_extension>"; exit 1; }

[ ! -d "$1" ] && { echo "Error: $1 does not exist or is not a directory."; exit 1; }

echo "Files with extension .$2 in $1:"

for file in "$1"/*."$2"; do
  size=$(stat -c %s "$file")
  echo "$(basename "$file"): $((size / 1024)) KB"
done
'''

BATCH_SAMPLE = '''@echo off

REM This script takes two arguments: a directory and a file extension.
REM It finds all the files in the directory that have the given extension
REM and prints out their names and sizes.

if "%~2" == "" (
  echo Usage: %0 directory file_extension
  exit /b 1
)

if not exist %1 (
  echo Error: %1 does not exist or is not a directory.
  exit /b 1
)

echo Files with extension %2 in %1:

for %%f in (%1\\*.%2) do (
  for /f "tokens=3" %%s in ('dir /a:-d /b "%%f" ^| find "File(s)"') do (
    echo %%~nxf: %%s bytes
  )
)

echo Done.
'''

LANGUAGES = ('Python', 'QGIS 表达式', 'SQL', 'HTML', 'CSS', 'JavaScript', 'R', 'Bash', 'Batch')
PREVIEWS = (('mPythonPreview', QgsCodeEditorPython, PYTHON_SAMPLE),
            ('mExpressionPreview', QgsCodeEditorExpression, EXPRESSION_SAMPLE),
            ('mSQLPreview', QgsCodeEditorSQL, SQL_SAMPLE),
            ('mHtmlPreview', QgsCodeEditorHTML, HTML_SAMPLE),
            ('mCssPreview', QgsCodeEditorCSS, CSS_SAMPLE),
            ('mJsPreview', QgsCodeEditorJavascript, JS_SAMPLE),
            ('mRPreview', QgsCodeEditorR, R_SAMPLE))


class QgsCodeEditorOptionsWidget(QgsOptionsPageWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        uic.loadUi(str(ROOT / 'ui/qgscodeditorsettings.ui'), self)
        self.setObjectName('mOptionsPageCodeEditor')
        settings = QgsSettings()
        # Populating the widgets must not write anything: native only persists in
        # apply(). Without this guard the setters below would fire their signals
        # and save on mere dialog construction (so Cancel would still apply).
        self.mInitialising = True

        self.mColorButtonMap = {}
        for roleName, widgetName in COLOR_ROLES:
            role = getattr(QgsCodeEditorColorScheme.ColorRole, roleName, None)
            widget = getattr(self, widgetName, None)
            if role is None or widget is None: continue
            widget.setAllowOpacity(True)
            self.mColorButtonMap[role] = widget

        self.mColorSchemeComboBox.addItem('默认', '')
        registry = QgsGui.codeEditorColorSchemeRegistry()
        nameToId = {}
        for schemeId in registry.schemes():
            scheme = registry.scheme(schemeId)
            if scheme is None: continue
            nameToId[scheme.name()] = schemeId
            self.mColorSchemeComboBox.addItem(scheme.name(), schemeId)
        self.mColorSchemeComboBox.addItem('自定义', 'custom')

        override = settings.value(OVERRIDE_COLORS, False, type=bool)
        if override:
            for role, widget in self.mColorButtonMap.items():
                widget.setColor(QgsCodeEditor.color(role))
            self.mColorSchemeComboBox.setCurrentIndex(
                self.mColorSchemeComboBox.findData('custom'))
        else:
            theme = settings.value(COLOR_SCHEME, '', type=str)
            self.mColorSchemeComboBox.setCurrentIndex(
                max(0, self.mColorSchemeComboBox.findData(theme)))
        self.mColorSchemeComboBox.currentIndexChanged.connect(self.onSchemeChanged)

        font = QgsCodeEditor.getMonospaceFont()
        self.mFontComboBox.setCurrentFont(font)
        self.mSizeSpin.setValue(font.pointSize())
        self.mOverrideFontGroupBox.setChecked(
            bool(settings.value(FONT_FAMILY, '', type=str)))
        self.mFontComboBox.currentIndexChanged.connect(self.onAppearanceChanged)
        self.mSizeSpin.valueChanged.connect(self.onAppearanceChanged)
        self.mOverrideFontGroupBox.toggled.connect(self.onAppearanceChanged)

        self.mBashPreview = QgsCodeEditorShell(None, QgsCodeEditor.Mode.ScriptEditor, Qgis.ScriptLanguage.Bash)
        self.mBatchPreview = QgsCodeEditorShell(None, QgsCodeEditor.Mode.ScriptEditor, Qgis.ScriptLanguage.Batch)
        from qgis.PyQt.QtWidgets import QVBoxLayout
        for page, preview in ((self.pageBash, self.mBashPreview), (self.pageBatch, self.mBatchPreview)):
            layout = QVBoxLayout()
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(preview)
            page.setLayout(layout)
        for name, _, sample in PREVIEWS:
            getattr(self, name).setText(sample)
        self.mBashPreview.setText(BASH_SAMPLE)
        self.mBatchPreview.setText(BATCH_SAMPLE)
        self.mListLanguage.addItems(LANGUAGES)
        self.mListLanguage.currentRowChanged.connect(self.mPreviewStackedWidget.setCurrentIndex)
        self.mListLanguage.setCurrentRow(0)
        self.mPreviewStackedWidget.setCurrentIndex(0)
        self.mSplitter.restoreState(settings.value(SPLITTER_STATE, b''))
        self.refreshSchemeColors()
        self.mInitialising = False

    def selectedScheme(self):
        return self.mColorSchemeComboBox.currentData() or ''

    def refreshSchemeColors(self):
        """Show the scheme's colours on the buttons, as native does."""
        theme = self.selectedScheme()
        for role, widget in self.mColorButtonMap.items():
            if theme != 'custom':
                widget.setColor(QgsCodeEditor.defaultColor(role, theme))

    def onSchemeChanged(self, *args):
        self.refreshSchemeColors()
        self.onAppearanceChanged()

    def onAppearanceChanged(self, *args):
        """Persist immediately and rebuild the previews, which read the settings."""
        if self.mInitialising: return
        self.persist()
        self.rebuildPreviews()

    def persist(self):
        settings = QgsSettings()
        theme = self.selectedScheme()
        custom = theme == 'custom'
        settings.setValue(OVERRIDE_COLORS, custom)
        if not custom:
            settings.setValue(COLOR_SCHEME, theme)
        for role, widget in self.mColorButtonMap.items():
            QgsCodeEditor.setColor(role, widget.color())
        if self.mOverrideFontGroupBox.isChecked():
            settings.setValue(FONT_FAMILY, self.mFontComboBox.currentFont().family())
            settings.setValue(FONT_SIZE, self.mSizeSpin.value())
        else:
            settings.remove(FONT_FAMILY)
            settings.remove(FONT_SIZE)

    def rebuildPreviews(self):
        """Recreate every preview so it picks up the scheme and font settings."""
        for name, factory, sample in PREVIEWS:
            self.replacePreview(name, factory(), sample)
        self.mBashPreview = self.replaceShell(self.mBashPreview, Qgis.ScriptLanguage.Bash, BASH_SAMPLE)
        self.mBatchPreview = self.replaceShell(self.mBatchPreview, Qgis.ScriptLanguage.Batch, BATCH_SAMPLE)

    def replacePreview(self, name, preview, sample):
        old = getattr(self, name)
        preview.setText(sample)
        parent = old.parentWidget()
        if parent is not None and parent.layout() is not None:
            parent.layout().replaceWidget(old, preview)
        old.deleteLater()
        preview.show()
        setattr(self, name, preview)

    def replaceShell(self, old, language, sample):
        preview = QgsCodeEditorShell(None, QgsCodeEditor.Mode.ScriptEditor, language)
        preview.setText(sample)
        parent = old.parentWidget()
        if parent is not None and parent.layout() is not None:
            parent.layout().replaceWidget(old, preview)
        old.deleteLater()
        preview.show()
        return preview

    def apply(self):
        self.persist()
        QgsSettings().setValue(SPLITTER_STATE, self.mSplitter.saveState())
