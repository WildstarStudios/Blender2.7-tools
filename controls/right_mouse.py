# Combined Right Mouse Navigation addon for Blender 2.79b
# Ported from Blender 4.5 version

bl_info = {
    "name": "Right Mouse Navigation",
    "author": "WildstarStudios",
    "version": (1, 1),
    "blender": (2, 79, 0),
    "location": "View3D",
    "description": "Right mouse button navigation with context menu on release",
    "warning": "",
    "category": "3D View"
}

import bpy
from bpy.props import BoolProperty, FloatProperty
from bpy.types import Operator, AddonPreferences

addon_keymaps = []

# Preferences
class RightMouseNavigationPreferences(AddonPreferences):
    bl_idname = __name__

    time = FloatProperty(
        name="Time Threshold",
        description="How long you have to hold right mouse to open menu",
        default=0.3,
        min=0.1,
        max=10,
    )

    reset_cursor_on_exit = BoolProperty(
        name="Reset Cursor on Exit",
        description="After exiting navigation, this determines if the cursor stays "
        "where RMB was clicked (if unchecked) or resets to the center (if checked)",
        default=False,
    )

    return_to_ortho_on_exit = BoolProperty(
        name="Return to Orthographic on Exit",
        description="After exiting navigation, this determines if the Viewport "
        "returns to Orthographic view (if checked) or remains in Perspective view (if unchecked)",
        default=True,
    )

    enable_for_node_editors = BoolProperty(
        name="Enable for Node Editors",
        description="Right Mouse will pan the view / open the Node Add/Search Menu",
        default=False,
    )

    disable_camera_navigation = BoolProperty(
        name="Disable Navigation for Camera View",
        description="Enable if you only want to navigate your scene, and not affect Camera Transform",
        default=False,
    )

    show_cam_lock_ui = BoolProperty(
        name="Show Camera Navigation Lock button",
        description="Displays the Camera Navigation Lock button in the 3D Viewport",
        default=False,
    )

    def draw(self, context):
        layout = self.layout

        row = layout.row()
        box = row.box()
        box.label(text="Menu / Movement", icon="DRIVER_DISTANCE")
        box.prop(self, "time")
        box = row.box()
        box.label(text="Node Editor", icon="NODETREE")
        box.prop(self, "enable_for_node_editors")

        row = layout.row()
        box = row.box()
        box.label(text="Cursor", icon="CURSOR")
        box.prop(self, "reset_cursor_on_exit")
        box = row.box()
        box.label(text="View", icon="VIEW3D")
        box.prop(self, "return_to_ortho_on_exit")

        row = layout.row()
        box = row.box()
        box.label(text="Camera", icon="CAMERA_DATA")
        box.prop(self, "disable_camera_navigation")
        box.prop(self, "show_cam_lock_ui")

# Operators
class RMN_OT_right_mouse_navigation(Operator):
    """Timer that decides whether to display a menu after Right Click"""
    bl_idname = "rmn.right_mouse_navigation"
    bl_label = "Right Mouse Navigation"
    bl_options = {"REGISTER", "UNDO"}

    _timer = None
    _count = 0
    _finished = False
    _callMenu = False
    _ortho = False
    _back_to_ortho = False
    _mouse_moved = False
    _start_x = 0
    _start_y = 0
    
    # Updated menu names for Blender 2.79b
    menu_by_mode = {
        "OBJECT": "VIEW3D_MT_object_specials",
        "EDIT_MESH": "VIEW3D_MT_edit_mesh_specials",
        "EDIT_SURFACE": "VIEW3D_MT_edit_curve_specials",
        "EDIT_TEXT": "VIEW3D_MT_edit_font_specials",
        "EDIT_ARMATURE": "VIEW3D_MT_edit_armature_specials",
        "EDIT_CURVE": "VIEW3D_MT_edit_curve_specials",
        "EDIT_METABALL": "VIEW3D_MT_edit_metaball_specials",
        "EDIT_LATTICE": "VIEW3D_MT_edit_lattice_specials",
        "POSE": "VIEW3D_MT_pose_specials",
        "PAINT_VERTEX": "VIEW3D_MT_vertex_specials",
        "PAINT_WEIGHT": "VIEW3D_MT_weight_specials",
        "PAINT_TEXTURE": "VIEW3D_MT_paint_specials",
        "SCULPT": "VIEW3D_MT_sculpt_specials",
    }

    def modal(self, context, event):
        preferences = context.user_preferences
        addon_prefs = preferences.addons[__name__].preferences
        enable_nodes = addon_prefs.enable_for_node_editors

        space_type = context.space_data.type

        # Check if mouse moved significantly
        if event.type == 'MOUSEMOVE' and not self._mouse_moved:
            if abs(event.mouse_x - self._start_x) > 5 or abs(event.mouse_y - self._start_y) > 5:
                self._mouse_moved = True

        if space_type == "VIEW_3D":
            if context.space_data.region_3d.is_perspective:
                self._ortho = False
            else:
                self._back_to_ortho = addon_prefs.return_to_ortho_on_exit

        if self._finished:
            def reset_cursor():
                area = context.area
                x = area.x
                y = area.y
                x += int(area.width / 2)
                y += int(area.height / 2)
                context.window.cursor_warp(x, y)

            if self._callMenu:
                if addon_prefs.reset_cursor_on_exit and not space_type == "NODE_EDITOR":
                    reset_cursor()
                self.callMenu(context)
            else:
                if addon_prefs.reset_cursor_on_exit:
                    reset_cursor()

            if self._back_to_ortho:
                bpy.ops.view3d.view_persportho()

            return {"CANCELLED"}

        if space_type == "VIEW_3D" or (space_type == "NODE_EDITOR" and enable_nodes):
            if event.type in {"RIGHTMOUSE"}:
                if event.value in {"RELEASE"}:
                    context.window.cursor_modal_restore()
                    
                    # If mouse didn't move much AND time threshold not met, show menu
                    if not self._mouse_moved and self._count < addon_prefs.time:
                        self._callMenu = True
                    else:
                        # Mouse moved - navigation completed, don't show menu
                        self._callMenu = False
                    
                    self.cancel(context)
                    self._finished = True
                    return {"PASS_THROUGH"}

            if event.type == "TIMER":
                if self._count <= addon_prefs.time:
                    self._count += 0.1
            return {"PASS_THROUGH"}
        
        return {"PASS_THROUGH"}

    def callMenu(self, context):
        select_mouse = context.user_preferences.inputs.select_mouse
        space_type = context.space_data.type

        if select_mouse == "LEFT":
            if space_type == "NODE_EDITOR":
                node_tree = context.space_data.node_tree
                if node_tree:
                    if node_tree.nodes.active is not None and node_tree.nodes.active.select:
                        bpy.ops.wm.call_menu(name="NODE_MT_context_menu")
                    else:
                        bpy.ops.wm.call_menu(name="NODE_MT_add_search")
            else:
                try:
                    bpy.ops.wm.call_menu(name=self.menu_by_mode[context.mode])
                except (RuntimeError, KeyError):
                    # Fallback for any mode
                    try:
                        bpy.ops.wm.call_menu(name="VIEW3D_MT_specials")
                    except:
                        pass
        else:
            if space_type == "VIEW_3D":
                bpy.ops.view3d.select("INVOKE_DEFAULT")

    def invoke(self, context, event):
        # Store initial mouse position and cursor
        self._start_x = event.mouse_x
        self._start_y = event.mouse_y
        self._mouse_moved = False
        self._count = 0
        self._finished = False
        self._callMenu = False
        
        return self.execute(context)

    def execute(self, context):
        preferences = context.user_preferences
        addon_prefs = preferences.addons[__name__].preferences
        enable_nodes = addon_prefs.enable_for_node_editors
        disable_camera = addon_prefs.disable_camera_navigation

        space_type = context.space_data.type

        if space_type == "VIEW_3D":
            view = context.space_data.region_3d.view_perspective
            if not (view == "CAMERA" and disable_camera):
                try:
                    # Use fly navigation instead of walk - it confirms on right mouse release
                    bpy.ops.view3d.walk('INVOKE_DEFAULT')
                    
                    wm = context.window_manager
                    self._timer = wm.event_timer_add(0.1, window=context.window)
                    wm.modal_handler_add(self)
                    return {"RUNNING_MODAL"}
                except RuntimeError as e:
                    self.report({"ERROR"}, "Cannot navigate: " + str(e))
                    return {"CANCELLED"}
            else:
                return {"CANCELLED"}

        elif space_type == "NODE_EDITOR" and enable_nodes:
            bpy.ops.view2d.pan("INVOKE_DEFAULT")
            wm = context.window_manager
            self._timer = wm.event_timer_add(0.01, window=context.window)
            wm.modal_handler_add(self)
            return {"RUNNING_MODAL"}

        elif space_type == "IMAGE_EDITOR":
            try:
                bpy.ops.wm.call_menu(name="VIEW3D_MT_paint_specials")
            except:
                pass
            return {"FINISHED"}
        
        return {"CANCELLED"}

    def cancel(self, context):
        wm = context.window_manager
        if self._timer:
            wm.event_timer_remove(self._timer)

class RMN_OT_toggle_cam_navigation(Operator):
    """Turn Mouse Navigation of Camera On and Off"""
    bl_idname = "rmn.toggle_cam_navigation"
    bl_label = "Toggle Mouse Camera Navigation"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        context.user_preferences.addons[__name__].preferences.disable_camera_navigation = (
            not context.user_preferences.addons[__name__].preferences.disable_camera_navigation
        )
        return {"FINISHED"}

# UI Drawing function
def draw_cam_lock(self, context):
    preferences = context.user_preferences
    addon_prefs = preferences.addons[__name__].preferences
    cam_nav = addon_prefs.disable_camera_navigation

    layout = self.layout

    row = layout.row(align=True)
    row.alert = cam_nav
    col = row.column()
    col.scale_x = 1.3
    icon = "UNLOCKED" if cam_nav else "LOCKED"
    row.operator(text="", operator="rmn.toggle_cam_navigation", icon=icon)

    row = row.row(align=True)
    row.label(text="", icon="CAMERA_DATA")
    row.label(text="", icon="MOUSE_MOVE")

# Registration
classes = [
    RightMouseNavigationPreferences,
    RMN_OT_right_mouse_navigation,
    RMN_OT_toggle_cam_navigation,
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    # Add UI to header if enabled
    preferences = bpy.context.user_preferences
    addon_prefs = preferences.addons[__name__].preferences
    if addon_prefs.show_cam_lock_ui:
        bpy.types.VIEW3D_HT_header.append(draw_cam_lock)

    # Keymaps
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if kc:
        km = kc.keymaps.new(name="3D View", space_type="VIEW_3D")
        kmi = km.keymap_items.new("rmn.right_mouse_navigation", "RIGHTMOUSE", "PRESS")
        kmi.active = True

        km2 = kc.keymaps.new(name="Node Editor", space_type="NODE_EDITOR")
        kmi2 = km2.keymap_items.new("rmn.right_mouse_navigation", "RIGHTMOUSE", "PRESS")
        kmi2.active = False

        addon_keymaps.append((km, kmi))
        addon_keymaps.append((km2, kmi2))

    # Disable default right mouse menus
    active_kc = wm.keyconfigs.active
    if active_kc:
        menumodes = [
            "Object Mode",
            "Mesh",
            "Curve",
            "Armature", 
            "Metaball",
            "Lattice",
            "Font",
            "Pose",
        ]
        panelmodes = [
            "Vertex Paint",
            "Weight Paint",
            "Image Paint",
            "Sculpt",
        ]

        for mode in menumodes:
            if mode in active_kc.keymaps:
                for key in active_kc.keymaps[mode].keymap_items:
                    if key.type == "RIGHTMOUSE" and key.active:
                        key.active = False

        for mode in panelmodes:
            if mode in active_kc.keymaps:
                for key in active_kc.keymaps[mode].keymap_items:
                    if key.type == "RIGHTMOUSE" and key.active:
                        key.active = False

def unregister():
    # Remove UI
    try:
        bpy.types.VIEW3D_HT_header.remove(draw_cam_lock)
    except:
        pass

    # Restore default keymaps
    wm = bpy.context.window_manager
    active_kc = wm.keyconfigs.active
    if active_kc:
        menumodes = [
            "Object Mode",
            "Mesh",
            "Curve",
            "Armature",
            "Metaball", 
            "Lattice",
            "Font",
            "Pose",
            "Node Editor",
        ]
        panelmodes = [
            "Vertex Paint",
            "Weight Paint",
            "Image Paint",
            "Sculpt",
        ]

        for mode in menumodes:
            if mode in active_kc.keymaps:
                for key in active_kc.keymaps[mode].keymap_items:
                    if key.type == "RIGHTMOUSE":
                        key.active = True

        for mode in panelmodes:
            if mode in active_kc.keymaps:
                for key in active_kc.keymaps[mode].keymap_items:
                    if key.type == "RIGHTMOUSE":
                        key.active = True

    # Remove keymaps
    for km, kmi in addon_keymaps:
        km.keymap_items.remove(kmi)
    addon_keymaps.clear()

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()
