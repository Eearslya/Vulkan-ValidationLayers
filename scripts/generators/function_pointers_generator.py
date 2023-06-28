#!/usr/bin/python3 -i
#
# Copyright (c) 2015-2023 The Khronos Group Inc.
# Copyright (c) 2015-2023 Valve Corporation
# Copyright (c) 2015-2023 LunarG, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import sys
import os
from common_codegen import *
from generators.generator_utils import *
from generators.base_generator import BaseGenerator

class FunctionPointersOutputGenerator(BaseGenerator):
    def __init__(self,
                 errFile = sys.stderr,
                 warnFile = sys.stderr,
                 diagFile = sys.stdout):
        BaseGenerator.__init__(self, errFile, warnFile, diagFile)
        self.headerFile = False # Header file generation flag
        self.sourceFile = False # Source file generation flag

    def generate(self):
        self.headerFile = (self.filename == 'vk_function_pointers.h')
        self.sourceFile = (self.filename == 'vk_function_pointers.cpp')

        copyright = f'''{fileIsGeneratedWarning(os.path.basename(__file__))}
/***************************************************************************
*
* Copyright (c) 2015-2023 The Khronos Group Inc.
* Copyright (c) 2015-2023 Valve Corporation
* Copyright (c) 2015-2023 LunarG, Inc.
*
* Licensed under the Apache License, Version 2.0 (the "License");
* you may not use this file except in compliance with the License.
* You may obtain a copy of the License at
*
*     http://www.apache.org/licenses/LICENSE-2.0
*
* Unless required by applicable law or agreed to in writing, software
* distributed under the License is distributed on an "AS IS" BASIS,
* WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
* See the License for the specific language governing permissions and
* limitations under the License.
****************************************************************************/\n'''
        self.write(copyright)
        self.write('// NOLINTBEGIN') # Wrap for clang-tidy to ignore

        if self.headerFile:
            self.generateHeader()
        else:
            self.generateSource()

        self.write('// NOLINTEND') # Wrap for clang-tidy to ignore

    def generateHeader(self):
        out = []
        out.append('''
#pragma once
#include <vulkan/vulkan.h>

#ifdef _WIN32
/* Windows-specific common code: */
// WinBase.h defines CreateSemaphore and synchapi.h defines CreateEvent
//  undefine them to avoid conflicts with VkLayerDispatchTable struct members.
#ifdef CreateSemaphore
#undef CreateSemaphore
#endif
#ifdef CreateEvent
#undef CreateEvent
#endif
#endif

namespace vk {
''')
        for command in self.vk.commands.values():
            out.extend([f'#ifdef {command.protect}\n'] if command.protect else [])
            out.append(f'extern PFN_{command.name} {command.name[2:]};\n')
            out.extend([f'#endif //{command.protect}\n'] if command.protect else [])
        out.append('''
void InitCore(const char *api_name);
void InitInstanceExtension(VkInstance instance, const char* extension_name);
void InitDeviceExtension(VkInstance instance, VkDevice device, const char* extension_name);
void ResetAllExtensions();

} // namespace vk''')
        self.write("".join(out))

    def generateSource(self):
        out = []
        out.append('''
#include "vk_function_pointers.h"
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <functional>
#include <string>
#include "containers/custom_containers.h"

#ifdef _WIN32
// Dynamic Loading:
typedef HMODULE dl_handle;
static dl_handle open_library(const char *lib_path) {
    // Try loading the library the original way first.
    dl_handle lib_handle = LoadLibrary(lib_path);
    if (lib_handle == NULL && GetLastError() == ERROR_MOD_NOT_FOUND) {
        // If that failed, then try loading it with broader search folders.
        lib_handle = LoadLibraryEx(lib_path, NULL, LOAD_LIBRARY_SEARCH_DEFAULT_DIRS | LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR);
    }
    return lib_handle;
}
static char *open_library_error(const char *libPath) {
    static char errorMsg[164];
    (void)snprintf(errorMsg, 163, "Failed to open dynamic library \\\"%s\\\" with error %lu", libPath, GetLastError());
    return errorMsg;
}
static void *get_proc_address(dl_handle library, const char *name) {
    assert(library);
    assert(name);
    return (void *)GetProcAddress(library, name);
}
#elif defined(__linux__) || defined(__APPLE__) || defined(__FreeBSD__) || defined(__OpenBSD__) || defined(__QNX__)

#include <dlfcn.h>

typedef void *dl_handle;
static inline dl_handle open_library(const char *libPath) {
    // When loading the library, we use RTLD_LAZY so that not all symbols have to be
    // resolved at this time (which improves performance). Note that if not all symbols
    // can be resolved, this could cause crashes later. Use the LD_BIND_NOW environment
    // variable to force all symbols to be resolved here.
    return dlopen(libPath, RTLD_LAZY | RTLD_LOCAL);
}
static inline const char *open_library_error(const char * /*libPath*/) { return dlerror(); }
static inline void *get_proc_address(dl_handle library, const char *name) {
    assert(library);
    assert(name);
    return dlsym(library, name);
}
#else
#error Dynamic library functions must be defined for this OS.
#endif

namespace vk {
''')
        for command in self.vk.commands.values():
            out.extend([f'#ifdef {command.protect}\n'] if command.protect else [])
            out.append(f'PFN_{command.name} {command.name[2:]};\n')
            out.extend([f'#endif //{command.protect}\n'] if command.protect else [])

        out.append('''
void InitCore(const char *api_name) {

#if defined(WIN32)
    std::string filename = std::string(api_name) + "-1.dll";
    auto lib_handle = open_library(filename.c_str());
#elif(__APPLE__)
    std::string filename = std::string("lib") + api_name + ".dylib";
    auto lib_handle = open_library(filename.c_str());
#else
    std::string filename = std::string("lib") + api_name + ".so";
    auto lib_handle = open_library(filename.c_str());
    if (!lib_handle) {
        filename = std::string("lib") + api_name + ".so.1";
        lib_handle = open_library(filename.c_str());
    }
#endif

    if (lib_handle == nullptr) {
        printf("%s\\n", open_library_error(filename.c_str()));
        exit(1);
    }
''')
        out.extend([f'    {x.name[2:]} = reinterpret_cast<PFN_{x.name}>(get_proc_address(lib_handle, "{x.name}"));\n' for x in self.vk.commands.values() if not x.extension])
        out.append('}')

        out.append('''
void InitInstanceExtension(VkInstance instance, const char* extension_name) {
    assert(instance);
    static const vvl::unordered_map<std::string, std::function<void(VkInstance)>> initializers = {
''')
        for extension in [x for x in self.vk.extensions.values() if x.instance and x.commands]:
            out.extend([f'#ifdef {extension.protect}\n'] if extension.protect else [])
            out.append('        {\n')
            out.append(f'            "{extension.name}", [](VkInstance instance) {{\n')
            for command in [x for x in extension.commands]:
                out.append(f'                {command.name[2:]} = reinterpret_cast<PFN_{command.name}>(GetInstanceProcAddr(instance, "{command.name}"));\n')
            out.append('            }\n')
            out.append('        },\n')
            out.extend([f'#endif //{extension.protect}\n'] if extension.protect else [])

        out.append('''
    };

    if (auto it = initializers.find(extension_name); it != initializers.end())
        (it->second)(instance);
}
''')

        out.append('''
void InitDeviceExtension(VkInstance instance, VkDevice device, const char* extension_name) {
    static const vvl::unordered_map<std::string, std::function<void(VkInstance, VkDevice)>> initializers = {
''')
        for extension in [x for x in self.vk.extensions.values() if x.device and x.commands]:
            out.extend([f'#ifdef {extension.protect}\n'] if extension.protect else [])
            out.append('        {\n')
            out.append(f'            "{extension.name}", [](VkInstance, VkDevice device) {{\n')
            for command in [x for x in extension.commands]:
                out.append(f'                {command.name[2:]} = reinterpret_cast<PFN_{command.name}>(GetDeviceProcAddr(device, "{command.name}"));\n')
            out.append('            }\n')
            out.append('        },\n')
            out.extend([f'#endif //{extension.protect}\n'] if extension.protect else [])

        out.append('''
    };

    if (auto it = initializers.find(extension_name); it != initializers.end())
        (it->second)(instance, device);
}
''')

        out.append('void ResetAllExtensions() {\n')
        for command in [x for x in self.vk.commands.values() if x.extension is not None]:
            out.extend([f'#ifdef {command.protect}\n'] if command.protect else [])
            out.append(f'    {command.name[2:]} = nullptr;\n')
            out.extend([f'#endif //{command.protect}\n'] if command.protect else [])

        out.append('}\n')

        out.append('} // namespace vk')
        self.write(''.join(out))