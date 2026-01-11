import BinaryReader
import os
from DataHelper import *

import json
from pathlib import Path
from enum import Enum


class EPrimitiveType(Enum):
    TriangleList = 0
    TriangleStrip = 1
    QuadList = 2
    LineList = 3
    LineStrip = 4
    TriangleFan = 5
    RectList = 6


class ESecondaryMotionObjectType(Enum):
    Cloth = 0
    Chain = 1
    Jiggle = 2


class ESecondaryMotionSpringType(Enum):
    StructuralMisc = 0
    StructuralVertical = 1
    StructuralHorizontal = 2
    ShearDiagonal = 3
    Bend = 4
    BendVertical = 5


class XBGParser:
    def __init__(self, file_path):
        self.file_path = Path(file_path)
        self.meta = None
        self._reader = None
        self._mip_reader = None

    def _read_string_block(self, align=4):
        sid = self._reader.u32()
        size = self._reader.u32()
        value = self._reader.string(size)
        self._reader.align(align)
        return {"id": sid, "value": value}

    def _read_header(self):
        return {
            "magic": self._reader.u32(),
            "majorVersion": self._reader.u16(),
            "minorVersion": self._reader.u16(),
            "unk1": self._reader.u32(),
            "unk2": self._reader.u32(),
            "unk3": self._reader.u32(),
        }

    def _read_memory_need(self):
        return {
            "total": self._reader.u32(),
            "sceneMeshCount": self._reader.u32()
        }

    def _read_unknown_params(self):
        out = {
            "unk1": self._reader.f32(),
            "unk2": self._reader.u8()
        }
        self._reader.align(4)
        return out

    def _read_geom_params(self):
        out = {}

        out["meshDecompression"] = {
            "positionMin": self._reader.f32(),
            "positionRange": self._reader.f32(),
            "LocalHeight": self._reader.f32(),
        }

        out["uvDecompression"] = {
            "UVDecompressionXY": self._reader.f32(),
            "UVDecompressionZW": self._reader.f32(),
        }
        out["unk6"] = self._reader.f32()

        out["boundingSphere"] = sphere(self._reader)
        out["bboxMin"] = vec3(self._reader)
        out["bboxMax"] = vec3(self._reader)

        out["unk11"] = self._reader.u32()
        out["unk12"] = self._reader.u32()
        out["unk13"] = self._reader.u32()

        out["lodCount"] = self._reader.u32()
        out["lodDistances"] = [self._reader.f32() for _ in range(out["lodCount"])]

        out["killDistance"] = self._reader.f32()
        out["castShadow"] = self._reader.u8()
        out["showInReflection"] = self._reader.u8()
        out["pcSkuLodFlags"] = self._reader.u8()
        out["unk19"] = self._reader.u8()

        out["firstLowEndLOD"] = self._reader.u32()
        out["lowEndDistances"] = [
            self._reader.f32() for _ in range(out["lodCount"] - out["firstLowEndLOD"])
        ]

        return out

    def _read_materials(self):
        out = {"materials": [], "slots": []}

        count = self._reader.u32()
        for _ in range(count):
            out["materials"].append(self._read_string_block())

        slot_count = self._reader.u32()
        for _ in range(slot_count):
            entry = self._read_string_block()
            entry["slotIndex"] = self._reader.u32()
            out["slots"].append(entry)

        return out

    def _read_skins(self):
        skins = []
        count = self._reader.u32()
        for _ in range(count):
            sid = self._reader.u32()
            size = self._reader.u32()
            name = self._reader.string(size)
            self._reader.align(4)
            skins.append({"id": sid, "name": name})
        return skins

    def _read_bone_palettes(self):
        palettes = []
        count = self._reader.u32()
        for _ in range(count):
            bone_count = self._reader.u32()
            indices = [self._reader.u16() for _ in range(bone_count)]
            self._reader.align(4)
            palettes.append(indices)
        self._reader.align(4)
        return palettes

    def _read_skeletons(self):
        skels = []
        count = self._reader.u32()
        for _ in range(count):
            nodes = []
            node_count = self._reader.u32()
            for _ in range(node_count):
                boneLOD = self._reader.u8()
                self._reader.skip(3)
                pos = vec3(self._reader)
                rot = [self._reader.f32() for _ in range(4)]
                parent = self._reader.u16()
                mat_idx = self._reader.u16()
                nid = self._reader.u32()
                size = self._reader.u32()
                name = self._reader.string(size)
                self._reader.align(4)
                nodes.append({
                    "boneLOD": boneLOD,
                    "position": pos,
                    "rotation": rot,
                    "parent": parent,
                    "matrixIndex": mat_idx,
                    "id": nid,
                    "name": name
                })
            skels.append(nodes)

        matrices = {
            "rootIndex": self._reader.u32(),
            "count": self._reader.u32(),
            "matrices": []
        }
        self._reader.align(16)
        for _ in range(matrices["count"]):
            matrices["matrices"].append([self._reader.f32() for _ in range(16)])

        return {"skeletons": skels, "objectToBone": matrices}

    def _read_reflex(self):
        has = self._reader.u32()
        out = {"hasReflex": has}
        if has:
            size = self._reader.u32()
            out["data"] = self._reader.bytes(size)
            self._reader.align(4)
        return out

    def _read_smos(self):
        secondary_motion_objects = []
        count = self._reader.u32()
        for _ in range(count):
            simulation_parameters = {
                "gravity": vec3(self._reader),
                "verticalStiffness": self._reader.f32(),
                "horizontalStiffness": self._reader.f32(),
                "shearStiffness": self._reader.f32(),
                "bendStiffness": self._reader.f32(),
                "viscousDrag": self._reader.f32(),
                "aerodynamicDrag": self._reader.f32(),
                "internalFriction": self._reader.f32(),
                "jiggleStiffness": self._reader.f32(),
                "frictionCoefficient": self._reader.f32(),
                "frictionExtraRadius": self._reader.f32(),
                "numIterations": self._reader.u32(),
                "objectType": ESecondaryMotionObjectType(self._reader.u32()),
                "useMaxLengthConstraints": self._reader.u8()
            }
            self._reader.align(4)

            collision_primitive_collection_description = {
                "spheres": [],
                "cylinders": [],
                "capsules": [],
                "planes": []
            }
            sphereCount = self._reader.u32()
            collision_primitive_collection_description["sphereCount"] = sphereCount
            for _ in range(sphereCount):
                sphere = {
                    "primitive": self._read_string_block(16),
                    "primitiveToBone": [],
                }
                sphere["primitiveToBone"].append([self._reader.f32() for _ in range(16)])
                sphere["radius"] = self._reader.f32()
                collision_primitive_collection_description["spheres"].append(sphere)

            cylinderCount = self._reader.u32()
            collision_primitive_collection_description["cylinderCount"] = cylinderCount
            for _ in range(cylinderCount):
                cylinder = {
                    "primitive": self._read_string_block(16),
                    "primitiveToBone": [],
                }
                cylinder["primitiveToBone"].append([self._reader.f32() for _ in range(16)])
                cylinder["radius"] = self._reader.f32()
                cylinder["localPointA"] = vec3(self._reader)
                cylinder["localPointB"] = vec3(self._reader)
                collision_primitive_collection_description["cylinders"].append(cylinder)

            capsuleCount = self._reader.u32()
            collision_primitive_collection_description["capsuleCount"] = capsuleCount
            for _ in range(capsuleCount):
                capsule = {
                    "primitive": self._read_string_block(16),
                    "primitiveToBone": [],
                }
                capsule["primitiveToBone"].append([self._reader.f32() for _ in range(16)])
                capsule["radius"] = self._reader.f32()
                capsule["localPointA"] = vec3(self._reader)
                capsule["localPointB"] = vec3(self._reader)
                collision_primitive_collection_description["capsules"].append(capsule)

            planeCount = self._reader.u32()
            collision_primitive_collection_description["planeCount"] = planeCount
            for _ in range(planeCount):
                plane = {
                    "primitive": self._read_string_block(16),
                    "primitiveToBone": [],
                }
                plane["primitiveToBone"].append([self._reader.f32() for _ in range(16)])
                plane["localOrigin"] = vec3(self._reader)
                plane["localNormal"] = vec3(self._reader)
                collision_primitive_collection_description["planes"].append(plane)

            limit_collection_description = {
                "sphereLimits": [],
                "boxLimits": [],
                "cylinderLimits": []
            }
            sphereLimitCount = self._reader.u32()
            limit_collection_description["sphereLimitCount"] = sphereLimitCount
            for _ in range(sphereLimitCount):
                sphereLimit = {
                    "primitive": self._read_string_block(2),
                    "particleIndex": self._reader.u16(),
                    "offset": vec3(self._reader),
                }
                self._reader.align(4)
                sphereLimit["radius"] = self._reader.f32()
                limit_collection_description["sphereLimits"].append(sphereLimit)

            boxLimitCount = self._reader.u32()
            limit_collection_description["boxLimitCount"] = boxLimitCount
            for _ in range(boxLimitCount):
                boxLimit = {
                    "primitive": self._read_string_block(2),
                    "particleIndex": self._reader.u16(),
                    "offset": vec3(self._reader),
                }
                self._reader.align(4)
                boxLimit["halfRange"] = vec3(self._reader)
                limit_collection_description["boxLimits"].append(boxLimit)

            cylinderLimitCount = self._reader.u32()
            limit_collection_description["cylinderLimitCount"] = cylinderLimitCount
            for _ in range(cylinderLimitCount):
                cylinderLimit = {
                    "primitive": self._read_string_block(2),
                    "particleIndex": self._reader.u16(),
                    "offset": vec3(self._reader),
                }
                self._reader.align(4)
                cylinderLimit["localDirection"] = vec3(self._reader)
                cylinderLimit["length"] = self._reader.f32()
                cylinderLimit["radius"] = self._reader.f32()
                limit_collection_description["cylinderLimits"].append(cylinderLimit)

            particles = {
                "particle": [],
            }
            particleCount = self._reader.u32()
            particles["particleCount"] = particleCount
            for _ in range(particleCount):
                particle = {
                    "name": self._read_string_block(4),
                    "radius": self._reader.f32(),
                    "isAttached": self._reader.u16(),
                    "teleportParentBoneIndex": self._reader.u16(),
                    "texCoordinate": vec2(self._reader)
                }
                particles["particle"].append(particle)

            teleport_parent_bones = {
                "teleportParentBones": [],
            }
            boneCount = self._reader.u32()
            teleport_parent_bones["boneCount"] = boneCount
            for _ in range(boneCount):
                teleport_parent_bone = {
                    "name": self._read_string_block(4),
                }
                teleport_parent_bones["teleportParentBones"].append(teleport_parent_bone)

            triangles_descs = {
                "triangleDesc": [],
            }
            triangleDescCount = self._reader.u32()
            triangles_descs["triangleDescCount"] = triangleDescCount
            for _ in range(triangleDescCount):
                triangles_desc = {
                    "index1": self._reader.u16(),
                    "index2": self._reader.u16(),
                    "index3": self._reader.u16(),
                }
                triangles_descs["triangleDesc"].append(triangles_desc)
            self._reader.align(4)

            connectivities = {
                "neighbor": [],
            }
            connectivityCount = self._reader.u32()
            connectivities["connectivityCount"] = connectivityCount
            for _ in range(connectivityCount):
                connectivities["neighbor"].append(self._reader.u16())

            spring_descs = {
                "spring": [],
            }
            springCount = self._reader.u32()
            spring_descs["springCount"] = springCount
            for _ in range(springCount):
                spring_desc = {
                    "index1": self._reader.u16(),
                    "index2": self._reader.u16(),
                    "springType": ESecondaryMotionSpringType(self._reader.u16()),
                }
                spring_descs["spring"].append(spring_desc)

            secondary_motion_object = {
                "simulationParameters": simulation_parameters,
                "collisionPrimitiveCollectionDescription": collision_primitive_collection_description,
                "limitCollectionDescription": limit_collection_description,
                "particles": particles,
                "teleportParentBones": teleport_parent_bones,
                "connectivities": connectivities,
                "springs": spring_descs,
                "numStructuralVerticalSprings": self._reader.u16(),
                "isHandInPocketCompatible": self._reader.u16(),
            }
            secondary_motion_objects.append(secondary_motion_object)
            self._reader.align(4)

        return {"secondaryMotionObject": secondary_motion_objects}

    def _read_procedural_nodes(self):
        procedural_nodes = {
            "node": [],
        }

        nodeCount = self._reader.u32()
        procedural_nodes["nodeCount"] = nodeCount

        for _ in range(nodeCount):
            node = {
                "boneIndex": self._reader.u16(),
                "proceduralNodeType": self._reader.u8(),
            }
            self._reader.skip(1)

            if node["proceduralNodeType"] == 1:
                node["t1_unk1"] = self._reader.u32()
                node["t1_unk2"] = self._reader.f32()
                node["t1_unk3"] = self._reader.u32()
                node["t1_unk4"] = self._reader.f32()

            elif node["proceduralNodeType"] == 2:
                node["t2_unk1"] = self._reader.u32()
                node["t2_unk2"] = self._reader.f32()

            elif node["proceduralNodeType"] == 3:
                node["t3_unk1"] = self._reader.u32()
                node["t3_unk2"] = self._reader.u32()
                node["t3_unk3"] = self._reader.f32()

            elif node["proceduralNodeType"] == 5:
                node["t5_unk1"] = self._reader.u32()
                node["t5_unk2"] = self._reader.u32()
                node["t5_unk3"] = self._reader.f32()
                node["t5_unk4"] = self._reader.f32()
                node["t5_unk5"] = self._reader.f32()
                node["t5_unk6"] = self._reader.f32()
                node["t5_unk7"] = self._reader.f32()
                node["t5_unk8"] = self._reader.f32()
                node["t5_unk9"] = self._reader.f32()

            elif node["proceduralNodeType"] == 6:
                node["t6_unk1"] = self._reader.u32()
                node["t6_unk2"] = self._reader.u32()
                node["t6_unk3"] = self._reader.u32()
                node["t6_unk4"] = self._reader.u32()
                node["t6_unk5"] = self._reader.u32()

            procedural_nodes["node"].append(node)

        return procedural_nodes

    def _read_basic_draw_call_range(self):
        return {
            "vertexBufferByteOffset": self._reader.u32(),
            "primitiveCount": self._reader.u32(),
            "indexCount": self._reader.u32(),
            "indexBufferStartIndex": self._reader.u32(),
            "vertexCount": self._reader.u16(),
            "minIndexValue": self._reader.u16(),
            "maxIndexValue": self._reader.u16(),
            "groupCount": self._reader.u16(),
        }

    def _read_draw_call_range(self):
        draw_call = {
            "drawCall": self._read_basic_draw_call_range(),
            "boundingSphere": sphere(self._reader),
            "bboxMin": vec3(self._reader),
            "bboxMax": vec3(self._reader),
            "name": self._read_string_block(4)
        }
        draw_call["skinIndex"] = self._reader.u16()
        draw_call["attachedBoneIndex"] = self._reader.u16()
        return draw_call

    def _read_scene_meshes(self, lod_count):
        lods = []
        for _ in range(lod_count):
            meshes = []
            numSceneMesh = self._reader.u32()
            for _ in range(numSceneMesh):
                mesh = {
                    "boundingSphere": sphere(self._reader),
                    "bboxMin": vec3(self._reader),
                    "bboxMax": vec3(self._reader),
                    "primitiveType": EPrimitiveType(self._reader.u32()),
                    "materialIndex": self._reader.u16(),
                    "fvf": self._reader.u16(),
                    "vertexSize": self._reader.u8(),
                    "unk9": self._reader.u8(),
                    "unk10": self._reader.u16(),
                    "boneMapIndex": self._reader.u32(),
                }
                mesh["Point"] = mesh["fvf"] & 0x1
                mesh["PointComp"] = (mesh["fvf"] & 0x2) >> 1
                mesh["UV"] = (mesh["fvf"] & 0x4) >> 2
                mesh["UVComp1"] = (mesh["fvf"] & 0x8) >> 3
                mesh["Skin"] = (mesh["fvf"] & 0x10) >> 4
                mesh["SkinExtra"] = (mesh["fvf"] & 0x20) >> 5
                mesh["SkinRigid"] = (mesh["fvf"] & 0x40) >> 6
                mesh["NormalComp"] = (mesh["fvf"] & 0x80) >> 7
                mesh["Color"] = (mesh["fvf"] & 0x100) >> 8
                mesh["TangentComp"] = (mesh["fvf"] & 0x200) >> 9
                mesh["BinormalComp"] = (mesh["fvf"] & 0x400) >> 10
                mesh["PackedFirstUV"] = (mesh["fvf"] & 0x800) >> 11
                mesh["UVComp2"] = (mesh["fvf"] & 0x1000) >> 12
                mesh["UVComp3"] = (mesh["fvf"] & 0x2000) >> 13
                mesh["Normal"] = (mesh["fvf"] & 0x4000) >> 14
                mesh["NormalModifiedComp"] = (mesh["fvf"] & 0x8000) >> 15

                mesh["mergedRanges"] = self._read_basic_draw_call_range()

                numRanges = self._reader.u32()
                mesh["numRanges"] = numRanges
                mesh["numSkins"] = self._reader.u32()   # use the max skin count always?
                mesh["unk13"] = self._reader.u32()

                mesh["ranges"] = []
                for _ in range(numRanges):
                    range_draw = self._read_draw_call_range()
                    mesh["ranges"].append(range_draw)

                meshes.append(mesh)
            lods.append(meshes)
        return lods

    def _read_buffers(self):
        buffers = {
            "gfxBuffer": [],
        }

        numBuffer = self._reader.u32()
        buffers["numBuffer"] = numBuffer

        for _ in range(numBuffer):
            buffer = {}

            vbuf_size = self._reader.u32()
            buffer["vbuf_size"] = vbuf_size
            buffer["vertexBuffer"] = self._reader.bytes(vbuf_size)
            self._reader.align(4)

            ibuf_size = self._reader.u32()
            buffer["ibuf_size"] = ibuf_size
            buffer["indexBuffer"] = self._reader.bytes(ibuf_size)
            self._reader.align(4)

            buffers["gfxBuffer"].append(buffer)

        return buffers

    def _read_mip(self):
        out = {"hasMips": self._reader.u32()}
        if out["hasMips"]:
            out["unk1"] = self._reader.u32()
            out["mipSize"] = self._reader.u32()
            out["pathID"] = self._reader.u32()
            size = self._reader.u32()
            out["path"] = self._reader.string(size)
            self._reader.align(4)
        return out

    def parse(self):

        directory = os.path.dirname(self.file_path)

        data = self.file_path.read_bytes()
        self._reader = BinaryReader.BinaryReader(data)
        self.meta = {}
        #self.meta["directory"] = Path(directory).resolve()
        self.meta["header"] = self._read_header()
        self.meta["memory"] = self._read_memory_need()
        self.meta["unknown"] = self._read_unknown_params()
        self.meta["geomParams"] = self._read_geom_params()
        self.meta["materials"] = self._read_materials()
        self.meta["skins"] = self._read_skins()
        self.meta["bonePalettes"] = self._read_bone_palettes()
        self.meta["skeletons"] = self._read_skeletons()
        self.meta["reflex"] = self._read_reflex()
        self.meta["secondaryMotionObjects"] = self._read_smos()
        self.meta["proceduralNodes"] = self._read_procedural_nodes()
        self.meta["meshes"] = self._read_scene_meshes(self.meta["geomParams"]["lodCount"])
        self.meta["mipCount"] = self._reader.u32()
        self.meta["buffers"] = self._read_buffers()
        self.meta["mip"] = self._read_mip()

        self.meta["mipResourceFound"] = 0
        if self.meta["mipCount"] > 0:
            # just assume xbgmip in the same folder
            mip_path = Path(os.path.join(Path(directory).resolve(), os.path.basename(self.meta["mip"]["path"])))

            if os.path.exists(mip_path):
                self.meta["mipResourceFound"] = 1
                # self.meta["buffers"]["numBuffer"] += self.meta["mipCount"]
                mip_data = mip_path.read_bytes()
                self._mip_reader = BinaryReader.BinaryReader(mip_data)
                self._mip_reader.skip(16)
                for i in range(0, self.meta["mipCount"]):
                    buffer = {}

                    vbuf_size = self._mip_reader.u32()
                    buffer["vbuf_size"] = vbuf_size
                    buffer["vertexBuffer"] = self._mip_reader.bytes(vbuf_size)
                    self._mip_reader.align(4)

                    ibuf_size = self._mip_reader.u32()
                    buffer["ibuf_size"] = ibuf_size
                    buffer["indexBuffer"] = self._mip_reader.bytes(ibuf_size)
                    self._mip_reader.align(4)

                    self.meta["buffers"]["gfxBuffer"].insert(i, buffer)
            else:
                print(f"Mip resource not found: {mip_path}")

        self.meta["clothWrinkleControlPatchBundles"] = self._reader.bytes(len(data) - self._reader.tell())

        return self.meta
