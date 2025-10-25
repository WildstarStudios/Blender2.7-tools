bl_info = {
    "name": "Grid Scale Controller",
    "author": "WildstarStudios",
    "version": (1, 0),
    "blender": (2, 79, 0),
    "location": "View3D > N-panel > Grid Scale",
    "description": "Simple grid scale control with buttons and custom input designed to pair with viewport controller",
    "category": "3D View"
}

import bpy

# Preset grid scale values
grid_presets = [0.1, 0.25, 0.50, 1.0, 2.0, 5.0, 10.0]
current_index = 3  # Default to 1.0

# Property group for custom scale input
class GridScaleProperties(bpy.types.PropertyGroup):
    custom_value = bpy.props.FloatProperty(
        name="Custom Scale",
        description="Enter a custom grid scale",
        default=grid_presets[current_index],
        min=0.001,
        max=1000.0
    )

# Function to apply grid scale to 3D view
def set_grid_scale(value):
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            space = area.spaces.active
            space.grid_scale = value

# Operator to increase grid scale
class GridScaleIncrease(bpy.types.Operator):
    bl_idname = "view3d.grid_scale_increase"
    bl_label = "Increase Grid Scale"

    def execute(self, context):
        global current_index
        current_index = min(current_index + 1, len(grid_presets) - 1)
        value = grid_presets[current_index]
        context.scene.grid_scale_props.custom_value = value
        set_grid_scale(value)
        return {'FINISHED'}

# Operator to decrease grid scale
class GridScaleDecrease(bpy.types.Operator):
    bl_idname = "view3d.grid_scale_decrease"
    bl_label = "Decrease Grid Scale"

    def execute(self, context):
        global current_index
        current_index = max(current_index - 1, 0)
        value = grid_presets[current_index]
        context.scene.grid_scale_props.custom_value = value
        set_grid_scale(value)
        return {'FINISHED'}

# Operator to apply custom grid scale
class GridScaleApply(bpy.types.Operator):
    bl_idname = "view3d.grid_scale_apply"
    bl_label = "Apply Custom Grid Scale"

    def execute(self, context):
        value = context.scene.grid_scale_props.custom_value
        set_grid_scale(value)
        return {'FINISHED'}

# UI Panel
class GridScalePanel(bpy.types.Panel):
    bl_label = "Grid Scale"
    bl_idname = "VIEW3D_PT_grid_scale"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Grid Scale"

    def draw(self, context):
        layout = self.layout
        props = context.scene.grid_scale_props

        row = layout.row(align=True)
        row.operator("view3d.grid_scale_decrease", icon='TRIA_LEFT', text="Decrease")
        row.operator("view3d.grid_scale_increase", icon='TRIA_RIGHT', text="Increase")

        layout.prop(props, "custom_value", text="Custom")
        layout.operator("view3d.grid_scale_apply", icon='FILE_TICK', text="Apply")

# Registration
def register():
    bpy.utils.register_class(GridScaleProperties)
    bpy.types.Scene.grid_scale_props = bpy.props.PointerProperty(type=GridScaleProperties)

    bpy.utils.register_class(GridScaleIncrease)
    bpy.utils.register_class(GridScaleDecrease)
    bpy.utils.register_class(GridScaleApply)
    bpy.utils.register_class(GridScalePanel)

def unregister():
    bpy.utils.unregister_class(GridScaleProperties)
    del bpy.types.Scene.grid_scale_props

    bpy.utils.unregister_class(GridScaleIncrease)
    bpy.utils.unregister_class(GridScaleDecrease)
    bpy.utils.unregister_class(GridScaleApply)
    bpy.utils.unregister_class(GridScalePanel)

if __name__ == "__main__":
    register()
