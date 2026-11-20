from PySide2 import QtCore, QtGui, QtWidgets
import pandas as pd


class PandasModel(QtCore.QAbstractTableModel):
    """
    Class to populate a table view with a pandas dataframe
    """
    def __init__(self, data, parent=None):
        QtCore.QAbstractTableModel.__init__(self, parent)
        # display only: never change the data's index (the time axis of the raw data is used for
        # peak selection; converting it to int in place shifted every peak window)
        self._data = data

    def rowCount(self, parent=None):
        return self._data.shape[0]

    def columnCount(self, parent=None):
        return self._data.shape[1]

    def data(self, index, role=QtCore.Qt.DisplayRole):
        if index.isValid():
            if role == QtCore.Qt.DisplayRole:
                return str(self._data.iloc[index.row(), index.column()])
        return None

    def headerData(self, i, orientation, role):
        if orientation == QtCore.Qt.Horizontal and role == QtCore.Qt.DisplayRole:
            return self._data.columns[i]
        if orientation == QtCore.Qt.Vertical and role == QtCore.Qt.DisplayRole:
            v = self._data.index[i]
            return f'{v:.3f}' if isinstance(v, float) else str(v)
        return None