import bpy
from math import floor, ceil, pi, sin, cos, pow, atan2, sqrt, acos

if "GridIcoSphere" in locals():
    import imp
    imp.reload( GridIcoSphere )
else:
    from . import GridIcoSphere

import bgl
import gpu
from gpu_extras.batch import batch_for_shader
from mathutils import Matrix, Vector

def toSRGB(value):
    if value <= 0.0031308:
        return value * 12.92
    else:
        return 1.055*pow(value, 1/2.4) - 0.055
    
def toLinear(value):
    if value <= 0.0404482362771082:
        return value / 12.92
    else:
        return pow(((value + 0.055) / 1.055), 2.4)

def linearToSRGB(color):
    return toSRGB(color[0]), toSRGB(color[1]), toSRGB(color[2])

def SRGBToLinear(color):
    return toLinear(color[0]), toLinear(color[1]), toLinear(color[2])

def colorNormalize(color, scale):
    outColor = [0.0, 0.0, 0.0]
    outColor[0] = color[0] * scale
    outColor[1] = color[1] * scale
    outColor[2] = color[2] * scale
    
    color_max = max(outColor)
    
    #color normalize
    if color_max > 1.0:
        outColor[0] /= color_max
        outColor[1] /= color_max
        outColor[2] /= color_max
    
    return linearToSRGB(outColor)

def bake_uv_to_vc(mesh, uv_layer, vertex_layer):

    lightmap = bpy.data.images.get("$lightmap")
    vertexmap = bpy.data.images.get("$vertmap")
    
    if lightmap == None or vertexmap == None:
        return False
    
    lm_width = lightmap.size[0]
    lm_height = lightmap.size[1]
    
    vt_width = vertexmap.size[0]
    vt_height = vertexmap.size[1]

    def _clamp_uv(val):
        return max(0, min(val, 1))

    lm_local_pixels = list(lightmap.pixels[:])
    vt_local_pixels = list(vertexmap.pixels[:])

    for face in mesh.polygons:
        mat_name = mesh.materials[face.material_index].name
        
        if mat_name.endswith(".vertex"):
            local_pixels = vt_local_pixels
            width = vt_width
            height = vt_height
        else:
            local_pixels = lm_local_pixels
            width = lm_width
            height = lm_height
        
        for vert_idx, loop_idx in zip(face.vertices, face.loop_indices):
            uv_coords = mesh.uv_layers[uv_layer].data[loop_idx].uv
            # Just sample the closest pixel to the UV coordinate
            # An improved approach might be to implement
            # bilinear sampling here instead
            target = [round(_clamp_uv(uv_coords.x) * (width - 1)), round(_clamp_uv(uv_coords.y) * (height - 1))]
            index = ( target[1] * width + target[0] ) * 4

            mesh.vertex_colors[vertex_layer].data[loop_idx].color[0] = local_pixels[index]
            mesh.vertex_colors[vertex_layer].data[loop_idx].color[1] = local_pixels[index + 1]
            mesh.vertex_colors[vertex_layer].data[loop_idx].color[2] = local_pixels[index + 2]
            mesh.vertex_colors[vertex_layer].data[loop_idx].color[3] = local_pixels[index + 3]
    return True

def storeLighmaps(bsp, n_lightmaps):
    lm_size = bsp.lightmap_size[0]
    color_components = 3
    color_scale = 1.0
    
    #get lightmap image
    image = bpy.data.images.get("$lightmap")
    local_pixels = list(image.pixels[:])
    
    packed_width, packed_height = image.size
    num_rows_colums = packed_width / lm_size
    numPixels = lm_size * lm_size * color_components
    lightmaps = [[0] * numPixels for i in range(n_lightmaps)]
    
    for pixel in range(packed_width*packed_height):
        #pixel position in packed texture
        row = pixel%packed_width
        colum = floor(pixel/packed_width)
        
        #lightmap quadrant
        quadrant_x = floor(row/lm_size)
        quadrant_y = floor(colum/lm_size)
        lightmap_id = floor(quadrant_x + (num_rows_colums * quadrant_y))
        
        if (lightmap_id > n_lightmaps-1) or (lightmap_id<0):
            continue
        else:
            #pixel id in lightmap
            lm_x = row%lm_size
            lm_y = colum%lm_size
            pixel_id = floor(lm_x + (lm_y * lm_size))
            
            outColor = colorNormalize([ local_pixels[4 * pixel + 0],
                                        local_pixels[4 * pixel + 1],
                                        local_pixels[4 * pixel + 2]],
                                        color_scale)
            if outColor[0] < 0 or outColor[0] > 1.0 or outColor[1] < 0 or outColor[1] > 1.0 or outColor[2] < 0 or outColor[2] > 1.0:
                print(outColor)
            lightmaps[lightmap_id][pixel_id*color_components + 0] = int(outColor[0] * 255)
            lightmaps[lightmap_id][pixel_id*color_components + 1] = int(outColor[1] * 255)
            lightmaps[lightmap_id][pixel_id*color_components + 2] = int(outColor[2] * 255)
            
            #lightmaps[lightmap_id][pixel_id*color_components + 3] = 1.0
            
    #for lightmap in range(n_lightmaps):
    #    image = bpy.data.images.new("lm_"+str(lightmap).zfill(4), width = lm_size, height = lm_size)
    #    image.pixels = lightmaps[lightmap]
    
    #clear lightmap lump
    bsp.lumps["lightmaps"].clear()
    clean_lms = [0.0 for i in range(128*128*3)]
    #fill lightmap lump
    for i in range(n_lightmaps):
        bsp.lumps["lightmaps"].add(lightmaps[i])
        
def create_lightgrid():
    
    bsp_group = bpy.data.node_groups.get("BspInfo")
    if bsp_group == None:
        return False
    
    lightgrid_origin = []
    lightgrid_origin.append(bsp_group.nodes["GridOrigin"].inputs[0].default_value)
    lightgrid_origin.append(bsp_group.nodes["GridOrigin"].inputs[1].default_value)
    lightgrid_origin.append(bsp_group.nodes["GridOrigin"].inputs[2].default_value)
    
    lightgrid_size = []
    lightgrid_size.append(bsp_group.nodes["GridSize"].inputs[0].default_value)
    lightgrid_size.append(bsp_group.nodes["GridSize"].inputs[1].default_value)
    lightgrid_size.append(bsp_group.nodes["GridSize"].inputs[2].default_value)
    
    lightgrid_dimensions = []
    lightgrid_dimensions.append(bsp_group.nodes["GridDimensions"].inputs[0].default_value)
    lightgrid_dimensions.append(bsp_group.nodes["GridDimensions"].inputs[1].default_value)
    lightgrid_dimensions.append(bsp_group.nodes["GridDimensions"].inputs[2].default_value)
    lightgrid_dimensions[1] /= lightgrid_dimensions[2]
                             
    lightgrid_inverse_dim = [   1.0 / lightgrid_dimensions[0],
                                1.0 / (lightgrid_dimensions[1]*lightgrid_dimensions[2]),
                                1.0 / lightgrid_dimensions[2] ]
    
    obj = GridIcoSphere.createGridIcoSphere()
    
    obj.location = lightgrid_origin
    obj.cycles_visibility.shadow = False
    
    #create the lightgrid points via arrays
    obj.modifiers.new("X_Array", type='ARRAY')
    obj.modifiers['X_Array'].use_constant_offset = True
    obj.modifiers['X_Array'].constant_offset_displace[0] = lightgrid_size[0]
    obj.modifiers['X_Array'].use_relative_offset = False
    obj.modifiers['X_Array'].count = lightgrid_dimensions[0]
    obj.modifiers['X_Array'].offset_u = lightgrid_inverse_dim[0]
    
    obj.modifiers.new("Y_Array", type='ARRAY')
    obj.modifiers['Y_Array'].use_constant_offset = True
    obj.modifiers['Y_Array'].constant_offset_displace[1] = lightgrid_size[1]
    obj.modifiers['Y_Array'].use_relative_offset = False
    obj.modifiers['Y_Array'].count = lightgrid_dimensions[1]
    obj.modifiers['Y_Array'].offset_v = lightgrid_inverse_dim[1]
    
    obj.modifiers.new("Z_Array", type='ARRAY')
    obj.modifiers['Z_Array'].use_constant_offset = True
    obj.modifiers['Z_Array'].constant_offset_displace[2] = lightgrid_size[2]
    obj.modifiers['Z_Array'].use_relative_offset = False
    obj.modifiers['Z_Array'].count = lightgrid_dimensions[2]
    obj.modifiers['Z_Array'].offset_v = lightgrid_inverse_dim[2]
    
    #scale the uv coordinates so it fits the lightgrid textures
    me = obj.data
    for loop in me.loops:
        me.uv_layers['UVMap'].data[loop.index].uv[0] *= lightgrid_inverse_dim[0]
        me.uv_layers['UVMap'].data[loop.index].uv[1] *= lightgrid_inverse_dim[1]
        
    for mat in me.materials:
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        
        node_image = nodes.new(type='ShaderNodeTexImage')
        node_image.location = -200,0
        image = bpy.data.images.get("$"+mat.name)
        if image == None:
            image = bpy.data.images.new("$"+mat.name, 
                                            width=lightgrid_dimensions[0], 
                                            height=lightgrid_dimensions[1]*lightgrid_dimensions[2],
                                            float_buffer=True)
        node_image.image = image
    return True
        
def encode_normal(normal):
    x, y, z = normal
    l = sqrt( ( x * x ) + ( y * y ) + ( z * z ) )
    if l == 0:
        print("zero length found!")
        return bytes((0, 0))
    x = x/l
    y = y/l
    z = z/l
    if x == 0 and y == 0:
        return 0, 0 if z > 0 else 128, 0
    long = int(round(atan2(y, x) * 255 / (2.0 * pi))) & 0xff
    lat  = int(round(acos(z) * 255 / (2.0 * pi))) & 0xff
    return lat, long

def storeLightgrid(bsp):
    #clear lightgrid data
    bsp.lumps["lightgrid"].clear()
    if bsp.use_lightgridarray:
        bsp.lumps["lightgridarray"].clear()
        
    vec_image = bpy.data.images.get("$Vector")
    dir_image = bpy.data.images.get("$Direct")
    amb_image = bpy.data.images.get("$Ambient")
    
    vec_pixels = vec_image.pixels[:]
    dir_pixels = dir_image.pixels[:]
    amb_pixels = amb_image.pixels[:]
    
    if vec_image == None or dir_image == None or amb_image == None:
        print("Images not properly baked for storing in the bsp")
        return None
    
    color_scale = 1.0
    current_pixel_mapping = 0
    hash_table = {}
    
    for pixel in range(vec_image.size[0] * vec_image.size[1]):
        #TODO: check if pixel in leaf
        
        x = vec_pixels[pixel * 4 + 0]
        y = vec_pixels[pixel * 4 + 1]
        z = vec_pixels[pixel * 4 + 2]
        
        lat, lon = encode_normal([x,y,z])
        
        amb = colorNormalize([  amb_pixels[4 * pixel + 0],
                                amb_pixels[4 * pixel + 1],
                                amb_pixels[4 * pixel + 2]],
                                color_scale)
                                
        dir = colorNormalize([  dir_pixels[4 * pixel + 0],
                                dir_pixels[4 * pixel + 1],
                                dir_pixels[4 * pixel + 2]],
                                color_scale)
        
        array = []
        if bsp.lightmaps == 4:
            array.append(int(amb[0] * 255))
            array.append(int(amb[1] * 255))
            array.append(int(amb[2] * 255))
            array.append(int(amb[0] * 255))
            array.append(int(amb[1] * 255))
            array.append(int(amb[2] * 255))
            array.append(int(amb[0] * 255))
            array.append(int(amb[1] * 255))
            array.append(int(amb[2] * 255))
            array.append(int(amb[0] * 255))
            array.append(int(amb[1] * 255))
            array.append(int(amb[2] * 255))
            array.append(int(dir[0] * 255))
            array.append(int(dir[1] * 255))
            array.append(int(dir[2] * 255))
            array.append(int(dir[0] * 255))
            array.append(int(dir[1] * 255))
            array.append(int(dir[2] * 255))
            array.append(int(dir[0] * 255))
            array.append(int(dir[1] * 255))
            array.append(int(dir[2] * 255))
            array.append(int(dir[0] * 255))
            array.append(int(dir[1] * 255))
            array.append(int(dir[2] * 255))
            array.append(0)
            array.append(0)
            array.append(0)
            array.append(0)
            array.append(lat)
            array.append(lon)
        else:
            array.append(int(amb[0] * 255))
            array.append(int(amb[1] * 255))
            array.append(int(amb[2] * 255))
            array.append(int(dir[0] * 255))
            array.append(int(dir[1] * 255))
            array.append(int(dir[2] * 255))
            array.append(lat)
            array.append(lon)
            
        if bsp.use_lightgridarray:
            current_hash = hash(tuple(array))
            found_twin = -1
            if current_hash in hash_table:
                found_twin = hash_table[current_hash]
                
            if found_twin == -1:
                bsp.lumps["lightgrid"].add(array)
                bsp.lumps["lightgridarray"].add([current_pixel_mapping])
                hash_table[current_hash] = current_pixel_mapping
                current_pixel_mapping += 1
            else:
                bsp.lumps["lightgridarray"].add([found_twin])
                
        else:
            bsp.lumps["lightgrid"].add(array)

def luma (color):
    return Vector.dot(color, Vector((0.299, 0.587, 0.114)))

def createLightGridTextures():
    image_names = [
        "Grid_00",
        "Grid_01",
        "Grid_02",
        "Grid_03",
        "Grid_04",
        "Grid_05",
        "Grid_06",
        "Grid_07",
        "Grid_08",
        "Grid_09",
        "Grid_10",
        "Grid_11",
        "Grid_12",
        "Grid_13",
        "Grid_14",
        "Grid_15",
        "Grid_16",
        "Grid_17",
        "Grid_18",
        "Grid_19",
        ]
    textures = [bpy.data.images.get("$"+img) for img in image_names]
    for tex in textures:
        if tex == None:
            return False
    
    width, height = textures[0].size
    
    buffer_names = [    "$Vector",
                        "$Direct",
                        "$Ambient"]
                        
    buffers = [bpy.data.images.get(img) for img in buffer_names]
    for i, buf in enumerate(buffers):
        if buf == None:
            buffers[i] = bpy.data.images.new(buffer_names[i], width=width, height=height, float_buffer=True)
    
    normals = [ Vector((-0.1876, 0.5773, 0.7947)),      # Grid_00
                Vector((-0.6071, 0.0000, 0.7947)),      # Grid_01
                Vector((-0.1876, -0.5773, 0.7947)),     # Grid_02
                Vector((0.4911, -0.3568, 0.7947)),      # Grid_03
                Vector((0.4911, 0.3568, 0.7947)),       # Grid_04
                Vector((0.7946, 0.5774, 0.1876)),       # Grid_05
                Vector((0.3035, 0.9342, -0.1876)),      # Grid_06
                Vector((-0.3035, 0.9342, 0.1876)),      # Grid_07
                Vector((-0.7947, 0.5774, -0.1876)),     # Grid_08
                Vector((-0.9822, 0.0000, 0.1876)),      # Grid_09
                Vector((-0.7947, -0.5774, -0.1876)),    # Grid_10
                Vector((-0.3035, -0.9342, 0.1876)),     # Grid_11
                Vector((0.3035, -0.9342, -0.1876)),     # Grid_12
                Vector((0.7947, -0.5774, 0.1876)),      # Grid_13
                Vector((0.9822, 0.0000, -0.1876)),      # Grid_14
                Vector((0.1876, -0.5774, -0.7947)),     # Grid_15
                Vector((0.6071, 0.0000, -0.7947)),      # Grid_16
                Vector((0.1876, 0.5774, -0.7947)),      # Grid_17
                Vector((-0.4911, 0.3568, -0.7947)),     # Grid_18
                Vector((-0.4911, -0.3568, -0.7947))     # Grid_19
                ]
    pixels = [  textures[0].pixels[:],
                textures[1].pixels[:],
                textures[2].pixels[:],
                textures[3].pixels[:],
                textures[4].pixels[:],
                textures[5].pixels[:],
                textures[6].pixels[:],
                textures[7].pixels[:],
                textures[8].pixels[:],
                textures[9].pixels[:],
                textures[10].pixels[:],
                textures[11].pixels[:],
                textures[12].pixels[:],
                textures[13].pixels[:],
                textures[14].pixels[:],
                textures[15].pixels[:],
                textures[16].pixels[:],
                textures[17].pixels[:],
                textures[18].pixels[:],
                textures[19].pixels[:]
                ]
                
    ambient_pixels = []
    direct_pixels = []
    vector_pixels = []
    
    for pixel in range(width*height):
        color_samples = [Vector((0.0, 0.0, 0.0)) for i in range(20)]
        for i, samples in enumerate(pixels):
            color_samples[i][0] = samples[pixel*4 + 0]
            color_samples[i][1] = samples[pixel*4 + 1]
            color_samples[i][2] = samples[pixel*4 + 2]
            
        avg_vec = Vector((0.0, 0.0, 0.0))
        for i in range(20):
            avg_vec += luma(color_samples[i]) * normals[i]
            
        Vector.normalize(avg_vec)
        
        direct_color = Vector((0.0, 0.0, 0.0))
        weight = 0.0
        for i in range(20):
            dot = max(0.0, Vector.dot(normals[i], avg_vec))
            if dot > 0.0:
                dot = sqrt(sqrt(dot))
            direct_color += color_samples[i] * dot
            weight += max(0.0, Vector.dot(normals[i], avg_vec))
            
        if weight != 0.0:
            direct_color /= weight
            
        ambient_color = Vector((0.0, 0.0, 0.0))
        for i in range(20):
            dot = max(0.0, Vector.dot(normals[i], avg_vec))
            if dot > 0.0:
                dot = sqrt(sqrt(dot))
            ambient_color += color_samples[i]
            ambient_color -= color_samples[i] * dot
        ambient_color /= 20.0;
        
        ambient_pixels.append(ambient_color[0])
        ambient_pixels.append(ambient_color[1])
        ambient_pixels.append(ambient_color[2])
        ambient_pixels.append(1.0)
        
        direct_pixels.append(direct_color[0])
        direct_pixels.append(direct_color[1])
        direct_pixels.append(direct_color[2])
        direct_pixels.append(1.0)
        
        vector_pixels.append(avg_vec[0])
        vector_pixels.append(avg_vec[1])
        vector_pixels.append(avg_vec[2])
        vector_pixels.append(1.0)
    
    buffers[0].pixels = vector_pixels
    buffers[1].pixels = direct_pixels
    buffers[2].pixels = ambient_pixels
    