# coding: utf-8
# /*##########################################################################
#
# Copyright (c) 2004-2016 European Synchrotron Radiation Facility
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#
# ###########################################################################*/
"""A QDialog widget to set-up the colormap.

It uses a description of colormaps as dict compatible with :class:`Plot`.

To run the following sample code, a QApplication must be initialized.

Create the colormap dialog and set the colormap description and data range:

>>> from silx.gui.plot.ColormapDialog import ColormapDialog

>>> dialog = ColormapDialog()

>>> dialog.setColormap(name='red', normalization='log',
...                    autoscale=False, vmin=1., vmax=2.)
>>> dialog.setDataRange(1., 100.)  # This scale the width of the plot area
>>> dialog.show()

Get the colormap description (compatible with :class:`Plot`) from the dialog:

>>> dialog.getColormap()
{'autoscale': False, 'name': 'red', 'vmin': 1.0, 'colors': 256, 'vmax': 2.0, 'normalization': 'linear'}

It is also possible to display an histogram of the image in the dialog.
This updates the data range with the range of the bins.

>>> import numpy
>>> image = numpy.random.normal(size=512 * 512).reshape(512, -1)
>>> hist, bin_edges = numpy.histogram(image, bins=10)
>>> dialog.setHistogram(hist, bin_edges)

The updates of the colormap description are also available through the signal:
:attr:`ColormapDialog.sigColormapChanged`.
"""

from __future__ import division

__authors__ = ["V.A. Sole", "T. Vincent"]
__license__ = "MIT"
__date__ = "29/03/2016"


import logging

import numpy

from .. import qt
from . import PlotWidget


_logger = logging.getLogger(__name__)


class _FloatEdit(qt.QLineEdit):
    """Field to edit a float value.

    :param float value: The value to set the QLineEdit to.
    :param parent: See :class:`QLineEdit`
    """
    def __init__(self, value=None, parent=None):
        qt.QLineEdit.__init__(self, parent)
        self.setValidator(qt.QDoubleValidator())
        self.setAlignment(qt.Qt.AlignRight)
        if value is not None:
            self.setValue(value)

    def value(self):
        """Return the QLineEdit current value as a float."""
        return float(self.text())

    def setValue(self, value):
        """Set the current value of the LineEdit

        :param float value: The value to set the QLineEdit to.
        """
        self.setText('%g' % value)


class ColormapDialog(qt.QDialog):
    """A QDialog widget to set the colormap.

    :param str title: The QDialog title 
    :param parent: See :class:`QDialog`
    """

    sigColormapChanged = qt.pyqtSignal(dict)
    """Signal triggered when the colormap is changed.

    It provides a dict describing the colormap to the slot.
    This dict can be used with :class:`Plot`.
    """

    def __init__(self, title="Colormap Dialog", parent=None):
        qt.QDialog.__init__(self, parent)
        self.setWindowTitle(title)

        self._histogramData = None
        self._minMaxWasEdited = False

        self._colormapList = ('gray', 'reversed gray', 'temperature',
                              'red', 'green', 'blue')

        self._dataRange = 1., 10.

        # Make the GUI
        vLayout = qt.QVBoxLayout(self)

        formWidget = qt.QWidget()
        vLayout.addWidget(formWidget)
        formLayout = qt.QFormLayout(formWidget)
        formLayout.setContentsMargins(10, 10, 10, 10)
        formLayout.setSpacing(0)

        # Colormap row
        self._comboBoxColormap = qt.QComboBox()
        for cmap in self._colormapList:
            # Capitalize first letters
            cmap = ' '.join(w[0].upper() + w[1:] for w in cmap.split())
            self._comboBoxColormap.addItem(cmap)
        self._comboBoxColormap.activated[int].connect(self._notify)
        formLayout.addRow('Colormap:', self._comboBoxColormap)

        # Normalization row
        self._normButtonLinear = qt.QRadioButton('Linear')
        self._normButtonLinear.setChecked(True)
        self._normButtonLog = qt.QRadioButton('Log')

        normButtonGroup = qt.QButtonGroup(self)
        normButtonGroup.setExclusive(True)
        normButtonGroup.addButton(self._normButtonLinear)
        normButtonGroup.addButton(self._normButtonLog)
        normButtonGroup.buttonClicked[int].connect(self._notify)

        normLayout = qt.QHBoxLayout()
        normLayout.setContentsMargins(0, 0, 0, 0)
        normLayout.setSpacing(10)
        normLayout.addWidget(self._normButtonLinear)
        normLayout.addWidget(self._normButtonLog)

        formLayout.addRow('Normalization:', normLayout)

        # Range row
        self._rangeAutoscaleButton = qt.QCheckBox('Autoscale')
        self._rangeAutoscaleButton.setChecked(True)
        self._rangeAutoscaleButton.toggled.connect(self._autoscaleToggled)
        self._rangeAutoscaleButton.clicked.connect(self._notify)
        formLayout.addRow('Range:', self._rangeAutoscaleButton)

        # Min row
        self._startValue = _FloatEdit(1.)
        self._startValue.setEnabled(False)
        self._startValue.textEdited.connect(self._minMaxTextEdited)
        self._startValue.editingFinished.connect(self._minMaxEditingFinished)
        formLayout.addRow('\tStart:', self._startValue)

        # Min row
        self._endValue = _FloatEdit(10.)
        self._endValue.setEnabled(False)
        self._endValue.textEdited.connect(self._minMaxTextEdited)
        self._endValue.editingFinished.connect(self._minMaxEditingFinished)
        formLayout.addRow('\tEnd:', self._endValue)

        # Add plot for histogram
        self._plotInit()
        vLayout.addWidget(self._plot)

        # Close button
        closeButton = qt.QPushButton('Close')
        closeButton.clicked.connect(self.accept)
        vLayout.addWidget(closeButton)

        # colormap window can not be resized
        self.setFixedSize(vLayout.minimumSize())

        # Set the colormap to default values
        self.setColormap(name='gray', normalization='linear',
                         autoscale=True, vmin=1., vmax=10.)

    def _plotInit(self):
        """Init the plot to display the range and the values"""
        self._plot = PlotWidget()
        #self._plot.setDataMargins(yMinMargin=0.125, yMaxMargin=0.125)
        self._plot.setGraphXLabel("Data Values")
        self._plot.setGraphYLabel("")
        self._plot.setInteractiveMode('select', zoomOnWheel=False)
        self._plot.enableActiveCurveHandling(False)
        self._plot.setMinimumSize(qt.QSize(250, 200))
        self._plot.sigPlotSignal.connect(self._plotSlot)

        self._plotUpdate()

    def _plotUpdate(self):
        """Update the plot content"""
        dataMin, dataMax = self.getDataRange()
        marge = (abs(dataMax) + abs(dataMin)) / 6.0
        minmd = dataMin - marge
        maxpd = dataMax + marge

        start, end = self._startValue.value(), self._endValue.value()

        if start < end:
            x = [minmd, start, end, maxpd]
            y = [0, 0, 1, 1]

        else:
            x = [minmd, end, start, maxpd]
            y = [1, 1, 0, 0]

        # Display the colormap on the side
        # colormap = {'name': self.getColormap()['name'],
        #             'normalization': self.getColormap()['normalization'],
        #             'autoscale': True, 'vmin': 1., 'vmax': 256.}
        # self._plot.addImage((1 + numpy.arange(256)).reshape(256, -1),
        #                     xScale=(minmd - marge, marge),
        #                     yScale=(1., 2./256.),
        #                     legend='colormap',
        #                     colormap=colormap)

        self._plot.addCurve(x, y,
                            legend="ConstrainedCurve",
                            color='black',
                            symbol='o',
                            linestyle='-',
                            resetZoom=False)

        draggable = not self._rangeAutoscaleButton.isChecked()

        self._plot.insertXMarker(
            self._startValue.value(),
            legend='Start',
            text='Start',
            draggable=draggable,
            color='blue')
            # constraint=lambda x, y: (max(x, minmd), y))
        self._plot.insertXMarker(
            self._endValue.value(),
            legend='End',
            text='End',
            draggable=draggable,
            color='blue')
            # constraint=lambda x, y: (max(x, minmd), y))

        self._plot.resetZoom()

    def _plotSlot(self, event):
        """Handle events from the plot"""
        if event['event'] in ('markerMoving', 'markerMoved'):
            value = float(str(event['xdata']))
            if event['label'] == 'Start':
                self._startValue.setValue(value)
            elif event['label'] == 'End':
                self._endValue.setValue(value)

            # This will recreate the markers while interacting...
            # It might break if marker interaction is changed
            if event['event'] == 'markerMoved':
                self._notify()
            else:
                self._plotUpdate()

    def getHistogram(self):
        """Returns the counts and bin edges of the displayed histogram.

        :return: (hist, bin_edges)
        :rtype: 2-tuple of numpy arrays"""
        if self._histogramData is None:
            return None
        else:
            bins, counts = self._histogramData
            return numpy.array(bins, copy=True), numpy.array(counts, copy=True)

    def setHistogram(self, hist=None, bin_edges=None):
        """Set the histogram to display.

        This update the data range with the bounds of the bins.
        See :meth:`setDataRange`.

        :param hist: array-like of counts or None to hide histogram
        :param bin_edges: array-like of bins edges or None to hide histogram
        """
        if hist is None or bin_edges is None:
            self._histogramData = None
            self._plot.removeCurve(legend='Histogram')

        else:
            hist = numpy.array(hist, copy=True)
            bin_edges = numpy.array(bin_edges, copy=True)
            self._histogramData = hist, bin_edges

            # For now, draw the histogram as a curve
            # using bin centers and normalised counts
            bins_center = 0.5 * (bin_edges[:-1] + bin_edges[1:])
            norm_hist = hist / max(hist)
            self._plot.addCurve(bins_center, norm_hist,
                                legend="Histogram",
                                color='gray',
                                symbol='',
                                linestyle='-',
                                fill=True)

            # Update the data range
            self.setDataRange(bin_edges[0], bin_edges[-1])

    def getDataRange(self):
        """Returns the data range used for the histogram area.

        :return: (dataMin, dataMax)
        :rtype: 2-tuple of float
        """
        return self._dataRange

    def setDataRange(self, min_, max_):
        """Set the range of data to use for the range of the histogram area.

        :param float min_: The min of the data
        :param float max_: The max of the data
        """
        min_, max_ = float(min_), float(max_)
        assert min_ <= max_
        self._dataRange = min_, max_
        if self._rangeAutoscaleButton.isChecked():
            self._startValue.setValue(min_)
            self._endValue.setValue(max_)
            self._notify()
        else:
            self._plotUpdate()

    def getColormap(self):
        """Return the colormap description as a dict.

        See :class:`Plot` for documentation on the colormap dict.
        """
        isNormLinear = self._normButtonLinear.isChecked()
        colormap = {
            'name': str(self._comboBoxColormap.currentText()).lower(),
            'normalization': 'linear' if isNormLinear else 'log',
            'autoscale': self._rangeAutoscaleButton.isChecked(),
            'vmin': self._startValue.value(),
            'vmax': self._endValue.value(),
            'colors': 256}
        return colormap

    def setColormap(self, name=None, normalization=None,
                    autoscale=None, vmin=None, vmax=None, colors=None):
        """Set the colormap description

        If some arguments are not provided, the current values are used.

        :param str name: The name of the colormap
        :param str normalization: 'linear' or 'log'
        :param bool autoscale: Toggle colormap range autoscale
        :param float vmin: The min value, ignored if autoscale is True
        :param float vmax: The max value, ignored if autoscale is True
        """
        if name is not None:
            assert name in self._colormapList
            index = self._colormapList.index(name)
            self._comboBoxColormap.setCurrentIndex(index)

        if normalization is not None:
            assert normalization in ('linear', 'log')
            self._normButtonLinear.setChecked(normalization == 'linear')

        if autoscale is not None:
            self._rangeAutoscaleButton.setChecked(autoscale)

        if vmin is not None:
            self._startValue.setValue(vmin)

        if vmax is not None:
            self._endValue.setValue(vmax)

        # Do it once for all the changes
        self._notify()

    def _notify(self, *args, **kwargs):
        """Emit the signal for colormap change"""
        self._plotUpdate()
        self.sigColormapChanged.emit(self.getColormap())

    def _autoscaleToggled(self, checked):
        """Handle autoscale changes by enabling/disabling min/max fields"""
        self._startValue.setEnabled(not checked)
        self._endValue.setEnabled(not checked)
        if checked:
            self._startValue.setValue(self._dataRange[0])
            self._endValue.setValue(self._dataRange[1])

    def _minMaxTextEdited(self, text):
        """Handle _startValue and _endValue textEdited signal"""
        self._minMaxWasEdited = True

    def _minMaxEditingFinished(self):
        """Handle _startValue and _endValue editingFinished signal

        Together with :meth:`_minMaxTextEdited`, this avoids to notify
        colormap change when the min and max value where not edited.
        """
        if self._minMaxWasEdited:
            self._minMaxWasEdited = False
            self._notify()
