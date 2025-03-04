"""
UI components and helper functions
"""

import wx
import logging
from typing import Optional, Callable, List, Tuple

logger = logging.getLogger('VideoDownloader.UI.Components')

class ProgressDialog(wx.Dialog):
    """Dialog to show download progress"""
    def __init__(self, parent, title: str, message: str):
        super(ProgressDialog, self).__init__(parent, title=title, size=(400, 150))
        
        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)
        
        self.message = wx.StaticText(panel, label=message)
        vbox.Add(self.message, 0, wx.ALL | wx.EXPAND, 10)
        
        self.gauge = wx.Gauge(panel, range=100, style=wx.GA_HORIZONTAL)
        vbox.Add(self.gauge, 0, wx.ALL | wx.EXPAND, 10)
        
        self.btn_cancel = wx.Button(panel, label="Cancel")
        self.btn_cancel.Bind(wx.EVT_BUTTON, self.on_cancel)
        vbox.Add(self.btn_cancel, 0, wx.ALIGN_CENTER | wx.ALL, 10)
        
        panel.SetSizer(vbox)
        self.Centre()
        
        # Callback for cancel
        self.on_cancel_callback = None
        
    def set_progress(self, value: int):
        """Set the progress value (0-100)"""
        self.gauge.SetValue(value)
        
    def set_message(self, message: str):
        """Update the message text"""
        self.message.SetLabel(message)
        
    def on_cancel(self, event):
        """Handle cancel button click"""
        if self.on_cancel_callback:
            self.on_cancel_callback()
        self.EndModal(wx.ID_CANCEL)
        
    def set_cancel_callback(self, callback: Callable):
        """Set the callback function for when cancel is clicked"""
        self.on_cancel_callback = callback


class URLDropTarget(wx.TextDropTarget):
    """Drop target for text URLs"""
    def __init__(self, text_ctrl):
        super(URLDropTarget, self).__init__()
        self.text_ctrl = text_ctrl
        
    def OnDropText(self, x, y, data):
        """Handle text drop"""
        current_text = self.text_ctrl.GetValue()
        if current_text:
            self.text_ctrl.SetValue(current_text + "\n" + data)
        else:
            self.text_ctrl.SetValue(data)
        return True


def create_bitmap_button(parent, bitmap_path: str, 
                        tooltip: str = "", size: Tuple[int, int] = (24, 24)) -> Optional[wx.BitmapButton]:
    """Create a button with a bitmap image"""
    try:
        bitmap = wx.Bitmap(bitmap_path)
        if bitmap.IsOk():
            btn = wx.BitmapButton(parent, bitmap=bitmap, size=wx.Size(size[0], size[1]))
            if tooltip:
                btn.SetToolTip(tooltip)
            return btn
        return None
    except Exception as e:
        logger.error(f"Error creating bitmap button: {e}")
        return None


def show_error_dialog(parent, message: str, title: str = "Error"):
    """Show an error dialog with the given message"""
    dlg = wx.MessageDialog(parent, message, title, wx.OK | wx.ICON_ERROR)
    dlg.ShowModal()
    dlg.Destroy()
    

def show_info_dialog(parent, message: str, title: str = "Information"):
    """Show an information dialog with the given message"""
    dlg = wx.MessageDialog(parent, message, title, wx.OK | wx.ICON_INFORMATION)
    dlg.ShowModal()
    dlg.Destroy()


def show_confirmation_dialog(parent, message: str, title: str = "Confirm") -> bool:
    """Show a confirmation dialog and return True if user selects Yes"""
    dlg = wx.MessageDialog(parent, message, title, wx.YES_NO | wx.ICON_QUESTION)
    result = dlg.ShowModal()
    dlg.Destroy()
    return result == wx.ID_YES