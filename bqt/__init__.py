"""
This Source Code Form is subject to the terms of the Mozilla Public
License, v. 2.0. If a copy of the MPL was not distributed with this
file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""

import atexit
import os
import sys
import ctypes
import bpy
import PySide2.QtCore as QtCore
from PySide2.QtWidgets import QApplication
from .blender_applications import BlenderApplication


# bpy.ops.bqt.return_focus
class QFocusOperator(bpy.types.Operator):
    bl_idname = "bqt.return_focus"
    bl_label = "Fix bug related to bqt focus"
    bl_description = "Fix bug related to bqt focus"
    bl_options = {'INTERNAL'}

    def __init__(self):
        super().__init__()

    def __del__(self):
        pass

    def invoke(self, context, event):
        """
        every time blender opens a new file, the context resets, losing the focus-hook.
        Re-instantiate the hook that returns focus to blender on alt tab bug

        ensure this is not called twice! or blender might crash on load new file
        """
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        """
        pass all events (e.g. keypress, mouse-move, ...) to detect_keyboard
        """
        self.detect_keyboard(event)
        return {"PASS_THROUGH"}

    def detect_keyboard(self, event):
        """
        detect when blender receives focus, and force a release of 'stuck' keys
        """

        self._qapp = QApplication.instance()
        if not self._qapp:
            print("QApplication not yet instantiated, focus hook can't be set")
            # wait until bqt has started the QApplication
            return

        if self._qapp.just_focused:
            self._qapp.just_focused = False

            # key codes from https://itecnote.com/tecnote/python-simulate-keydown/
            keycodes = [
                ('_ALT', 0x12),
                ('_CONTROL', 0x11),
                ('_SHIFT', 0x10),
                ('VK_LWIN', 0x5B),
                ('VK_RWIN', 0x5C),
            ]

            for name, code in keycodes:
                # if the first key pressed is one of the following,
                # don't simulate a key release, since it will cause a minor bug
                # (the first keypress on re-focus blender will be ignored, e.g. ctrl + v will just be v)
                if name not in event.type:
                    # safely release all other keys that might be stuck down
                    ctypes.windll.user32.keybd_event(code, 0, 2, 0)  # release key


# CORE FUNCTIONS #
def instantiate_application() -> BlenderApplication:
    """
    Create an instance of Blender Application

    Returns BlenderApplication: Application Instance

    """
    # enable dpi scale, run before creating QApplication
    QApplication.setHighDpiScaleFactorRoundingPolicy(QtCore.Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling)
    QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps)
    app = QApplication.instance()
    if not app:
        app = load_os_module()
    return app


def load_os_module() -> object:
    """
    Loads the correct OS platform Application Class

    Returns: Instance of BlenderApplication

    """
    operating_system = sys.platform
    if operating_system == 'darwin':
        from .blender_applications.darwin_blender_application import DarwinBlenderApplication

        return DarwinBlenderApplication(sys.argv)
    if operating_system in ['linux', 'linux2']:
        # TODO: LINUX module
        pass
    elif operating_system == 'win32':
        from .blender_applications.win32_blender_application import Win32BlenderApplication

        return Win32BlenderApplication(sys.argv)


@bpy.app.handlers.persistent
def add_focus_handle(dummy):
    # create a modal operator to return focus to blender to fix alt tab bug
    bpy.ops.bqt.return_focus('INVOKE_DEFAULT')


parent_window = None


@bpy.app.handlers.persistent
def create_global_app(dummy):
    """
    runs after blender finished startup
    """
    qapp = instantiate_application()

    # save a reference to the C++ window in a global var, to prevent the parent being garbage collected
    # for some reason this works here, but not in the blender_applications init as a class attribute (self),
    # and saving it in a global in blender_applications.py causes blender to crash on startup
    global parent_window
    parent_window = qapp._blender_window.parent()

    # after blender is wrapped in QWindow,
    # remove the  handle so blender is not wrapped again when opening a new scene
    bpy.app.handlers.load_post.remove(create_global_app)


def register():
    """
    setup bqt, wrap blender in qt, register operators
    """

    if os.getenv('BQT_DISABLE_STARTUP'):
        return

    # only start focus operator if blender is wrapped
    if not os.getenv('BQT_DISABLE_WRAP', 0):
        bpy.utils.register_class(QFocusOperator)

        # (re-)add focus handle after EVERY scene is loaded
        if add_focus_handle not in bpy.app.handlers.load_post:
            bpy.app.handlers.load_post.append(add_focus_handle)

    # append add_focus_handle before create_global_app,
    # else it doesn't run on blender startup
    # guessing that wrapping blender in QT interrupts load_post
    # resulting in the load_post handler not called on blender startup

    # use load_post since blender doesn't like data changed before scene is loaded,
    # wrap blender after first scene is loaded, the operator removes itself on first run
    if create_global_app not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(create_global_app)

    atexit.register(on_exit)


def unregister():
    """
    Unregister Blender Operator classes

    Returns: None

    """
    if not os.getenv('BQT_DISABLE_WRAP', 0) == "1":
        bpy.utils.unregister_class(focus.QFocusOperator)
    if create_global_app in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(create_global_app)
    if add_focus_handle in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(add_focus_handle)
    atexit.unregister(on_exit)


def on_exit():
    """Close BlenderApplication instance on exit"""
    app = QApplication.instance()
    if app:
        app.store_window_geometry()
        app.quit()