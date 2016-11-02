#!/usr/bin/env python

"""
Support for Elecraft KPod
"""


import os
import sys
import exceptions
import threading
import wx
import hid
import ctypes
import time

from struct import pack, unpack

GET_UPDATE_CMD = ord('u')
GET_ID_CMD = ord('=')
CONFIGURE_CMD = ord('C')
RESET_CMD = ord('r')
LED_AUX_CTRL = ord('O')
BEEP_CTRL = ord('Z')


class kpod(threading.Thread):
    """
    Interface to Elecraft KPod
    """
    def __init__(self, event_receiver=None, filename=None, **kwargs):
        self.event_receiver = event_receiver
        self.dev = None
        self.encoder = 0
        self.mute = 0
        self.scale = 0
        self.rocker = 3

        if not self._open_device(filename):
            raise exceptions.RuntimeError, 'Unable to find KPod'

        threading.Thread.__init__(self, **kwargs)
        self.keep_running = True
        self.start ()

    def close(self):
        if self.dev:
            self.dev.close()
        self.dev = None

    def _open_device(self, filename):
        self.dev = hid.Device(vid=0x4d8,pid=0xf12d)
        self.mute_device()
        return True

    def send_cmd(self, buff):
        self.dev.write(buff)
        return self.dev.read(8)

    def mute_device(self):
        cmd = CONFIGURE_CMD
        self.mute = 1
        opt = (self.scale << 1) | self.mute
        s = pack("BBBBBBBB", cmd, opt, 0, 0, 0, 0, 0, 0)
        buff = ctypes.create_string_buffer(s, 8)
        self.send_cmd(buff)

    def set_event_receiver(self, obj):
        self.event_receiver = obj

    def update_loop(self):
        cmd = GET_UPDATE_CMD

        s = pack("BBBBBBBB", cmd, 0, 0, 0, 0, 0, 0, 0)
        buff = ctypes.create_string_buffer(s, 8)

        POLL_INTERVAL = 50

        while (self.keep_running):
            time.sleep((POLL_INTERVAL*1.0)/1000.0)

            resp = self.send_cmd(buff)
            (cmd, ticks, controls, s0,s1,s2,s3) = unpack("=BhBBBBB", resp)
            if cmd != GET_UPDATE_CMD:
                continue

            if ticks:
                self.encoder += ticks
                self.on_rotate_post_event(self.encoder)

            tap_hold = (controls & 0x10) >> 4
            rocker = (controls & 0x60) >> 5
            buttons = controls & 0xf
            if (buttons):
                self.on_button_post_event(buttons, tap_hold)

            if self.rocker != rocker:
                self.rocker = rocker
                self.on_rocker_post_event(self.rocker)

    def run(self):
        try:
            self.update_loop()
        except hid.HIDException as err:
            raise
        except:
            if self.keep_running:
                exceptions.RuntimeError, 'An error during update_loop'
        finally:
            self.close()


class wx_kpod(kpod):
    def on_button_post_event(self, button, tap_hold):
        wx.PostEvent(self.event_receiver,
                     PMButtonEvent(button, tap_hold))

    def on_rotate_post_event(self, encoder):
        wx.PostEvent(self.event_receiver, PMRotateEvent(self.encoder))

    def on_rocker_post_event(self, rocker):
        wx.PostEvent(self.event_receiver, PMRockerEvent(self.rocker))


grEVT_BUTTON  = wx.NewEventType()
grEVT_ROTATE  = wx.NewEventType()
grEVT_ROCKER  = wx.NewEventType()

EVT_BUTTON = wx.PyEventBinder(grEVT_BUTTON, 0)
EVT_ROTATE = wx.PyEventBinder(grEVT_ROTATE, 0)
EVT_ROCKER = wx.PyEventBinder(grEVT_ROCKER, 0)

class PMButtonEvent(wx.PyEvent):
    def __init__(self, button, tap_hold):
        wx.PyEvent.__init__(self)
        self.SetEventType(grEVT_BUTTON)
        self.button = button
        self.tap_hold = tap_hold

    def Clone (self):
        self.__class__(self.GetId())


class PMRockerEvent(wx.PyEvent):
    def __init__(self, rocker):
        wx.PyEvent.__init__(self)
        self.SetEventType(grEVT_ROCKER)
        self.rocker = rocker

    def Clone (self):
        self.__class__(self.GetId())


class PMRotateEvent(wx.PyEvent):
    def __init__(self, encoder):
        wx.PyEvent.__init__(self)
        self.SetEventType (grEVT_ROTATE)
        self.encoder = encoder

    def Clone (self):
        self.__class__(self.GetId())


if __name__ == '__main__':
    class Frame(wx.Frame):
        def __init__(self,parent=None,id=-1,title='Title',
                     pos=wx.DefaultPosition, size=(400,200)):
            wx.Frame.__init__(self,parent,id,title,pos,size)
            EVT_BUTTON(self, self.on_button)
            EVT_ROTATE(self, self.on_rotate)
            EVT_ROCKER(self, self.on_rocker)

            self.Bind(wx.EVT_CLOSE, self._on_close)

            try:
                self.pm = wx_kpod(self)
            except:
                sys.stderr.write("Unable to find KPod\n")
                sys.exit(1)

        def on_button(self, evt):
            print "Button %d-%d" % (evt.button, evt.tap_hold)

        def on_rotate(self, evt):
            print "Rotated %d" % (evt.encoder,)

        def on_rocker(self, evt):
            print "Rocker %d" % (evt.rocker,)

        def _on_close(self, event):
            self.pm.close()
            event.Skip()

    class App(wx.App):
        def OnInit(self):
            title='Elecraft KPod Demo'
            self.frame = Frame(parent=None,id=-1,title=title)
            self.frame.Show()
            self.SetTopWindow(self.frame)
            return True

    app = App()
    app.MainLoop ()
