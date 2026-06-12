import re

class Instruction:
    def __init__(self, raw_text):
        self.raw_text = raw_text.strip()
        self.lhs = None
        self.opcode = None  # maps to the opcode (e.g. 'add')
        self.operands = []
        self.is_vector = False
        self.is_call = False
        self.called_function = None
        self.category = "Unknown"
        self.parse_instruction()
        self.categorize()

    def categorize(self):
        arithmetic_ops = {"add", "sub", "mul", "udiv", "sdiv", "urem", "srem", "fadd", "fsub", "fmul", "fdiv", "frem", "shl", "lshr", "ashr", "and", "or", "xor"}
        memory_ops = {"alloca", "load", "store", "getelementptr", "fence", "cmpxchg", "atomicrmw"}
        control_flow_ops = {"br", "switch", "ret", "indirectbr", "invoke", "callbr", "resume", "catchswitch", "catchret", "cleanupret"}
        function_ops = {"call", "invoke"}
        
        if self.opcode in arithmetic_ops:
            self.category = "Arithmetic"
        elif self.opcode in memory_ops:
            self.category = "Memory"
        elif self.opcode in control_flow_ops:
            self.category = "Control Flow"
        elif self.opcode in function_ops:
            self.category = "Function"
        elif self.is_vector:
            self.category = "Vector"
        elif self.opcode in {"icmp", "fcmp", "phi", "select"}:
            self.category = "Logic"

    def parse_instruction(self):
        # 1. Detect Vector operations
        if "<" in self.raw_text and "x" in self.raw_text and ">" in self.raw_text:
            self.is_vector = True
        
        # 2. Extract LHS and RHS
        if "=" in self.raw_text:
            parts = self.raw_text.split("=", 1)
            self.lhs = parts[0].strip()
            rhs = parts[1].strip()
        else:
            self.lhs = None
            rhs = self.raw_text

        # 3. Extract opcode
        words = rhs.split()
        if not words:
            self.opcode = ""
            return
            
        op_idx = 0
        modifiers = {"tail", "musttail", "notail", "volatile", "atomic", "weak", "linkonce"}
        while op_idx < len(words) and words[op_idx] in modifiers:
            op_idx += 1
            
        if op_idx < len(words):
            self.opcode = words[op_idx]
        else:
            self.opcode = words[0]
            
        # 4. Check function call
        if self.opcode == "call":
            self.is_call = True
            call_match = re.search(r'@([a-zA-Z0-9._]+)', rhs)
            if call_match:
                self.called_function = "@" + call_match.group(1)
                
        if self.opcode in ["shufflevector", "extractelement", "insertelement"]:
            self.is_vector = True

        # 5. Extract operands (strip LLVM types and keywords)
        clean_rhs = rhs
        
        # Remove types
        clean_rhs = re.sub(r'\bi\d+\b', '', clean_rhs)  # i32, i64, etc.
        clean_rhs = re.sub(r'\bfloat\b|\bdouble\b|\bvoid\b|\bhalf\b', '', clean_rhs)
        clean_rhs = re.sub(r'<[^>]+>', '', clean_rhs)  # vector types <4 x i32>
        clean_rhs = re.sub(r'\*+', '', clean_rhs)      # pointers
        
        # Remove standard modifiers
        keywords_to_remove = {"nsw", "nuw", "exact", "align", "tail", "musttail", "notail", "volatile", "atomic"}
        for kw in keywords_to_remove:
            clean_rhs = re.sub(r'\b' + kw + r'\b', '', clean_rhs)
            
        # Extract variables and literals
        op_matches = re.findall(r'%[a-zA-Z0-9._]+|@[a-zA-Z0-9._]+|\b-?\d+(?:\.\d+)?\b', clean_rhs)
        
        # Filter out opcode and LHS
        self.operands = [op for op in op_matches if op != self.opcode and op != self.lhs]

    def to_dict(self):
        return {
            "opcode": self.opcode,
            "operands": self.operands,
            "lhs": self.lhs,
            "raw_text": self.raw_text
        }

    def __repr__(self):
        return f"Instruction({self.lhs} = {self.opcode} ...)" if self.lhs else f"Instruction({self.opcode} ...)"


class BasicBlock:
    def __init__(self, label):
        self.label = label
        self.instructions = []
        self.predecessors = set()
        self.successors = []

    def add_instruction(self, inst):
        self.instructions.append(inst)

    def to_dict(self):
        return {
            "label": self.label,
            "successors": self.successors,
            "predecessors": list(self.predecessors),
            "instructions": [inst.to_dict() for inst in self.instructions]
        }

    def __repr__(self):
        return f"BasicBlock({self.label}, insts={len(self.instructions)}, succs={len(self.successors)})"


class Function:
    def __init__(self, name, return_type, args_section):
        self.name = name
        self.return_type = return_type
        self.args_section = args_section
        self.blocks = {}
        self.block_order = []

    def add_block(self, block):
        self.blocks[block.label] = block
        if block.label not in self.block_order:
            self.block_order.append(block.label)

    def build_cfg(self):
        """
        Parses branching and return instructions to connect predecessors and successors.
        """
        br_cond_re = re.compile(r'br\s+i1\s+[^,]+,\s*label\s+%(block_\d+),\s*label\s+%(block_\d+)')
        br_uncond_re = re.compile(r'br\s+label\s+%(block_\d+)')
        switch_re = re.compile(r'label\s+%(block_\d+)')

        for label in self.block_order:
            block = self.blocks[label]
            if not block.instructions:
                continue
                
            last_inst = block.instructions[-1].raw_text
            
            # Conditional branch
            cond_match = br_cond_re.search(last_inst)
            if cond_match:
                succs = [cond_match.group(1), cond_match.group(2)]
                for s in succs:
                    if s in self.blocks:
                        block.successors.append(s)
                        self.blocks[s].predecessors.add(label)
                continue
                
            # Unconditional branch
            uncond_match = br_uncond_re.search(last_inst)
            if uncond_match:
                succ = uncond_match.group(1)
                if succ in self.blocks:
                    block.successors.append(succ)
                    self.blocks[succ].predecessors.add(label)
                continue
                
            # Switch statement
            if last_inst.startswith("switch "):
                succs = switch_re.findall(last_inst)
                for s in succs:
                    if s in self.blocks:
                        block.successors.append(s)
                        self.blocks[s].predecessors.add(label)
                continue

    def to_dict(self):
        return {
            "name": self.name,
            "return_type": self.return_type,
            "args_section": self.args_section,
            "block_order": self.block_order,
            "blocks": {lbl: block.to_dict() for lbl, block in self.blocks.items()}
        }

    def __repr__(self):
        return f"Function({self.name}, blocks={len(self.blocks)})"


class Module:
    def __init__(self):
        self.functions = {}
        self.declarations = set()

    def add_function(self, func):
        self.functions[func.name] = func

    def add_declaration(self, name):
        self.declarations.add(name)

    def to_dict(self):
        return {
            "functions": {name: func.to_dict() for name, func in self.functions.items()},
            "declarations": list(self.declarations)
        }


class IRParser:
    def __init__(self):
        pass

    def parse(self, normalized_ir):
        """
        Parses normalized LLVM IR text into a Module object.
        """
        module = Module()
        lines = normalized_ir.splitlines()
        
        define_re = re.compile(r'^define\s+(.*?)\s+(@[a-zA-Z0-9._]+)\s*\(([^)]*)\)[^{]*\{')
        declare_re = re.compile(r'^declare\s+(.*?)\s+(@[a-zA-Z0-9._]+)')
        
        in_function = False
        current_func = None
        current_block = None
        
        for line in lines:
            trimmed = line.strip()
            if not trimmed:
                continue
                
            decl_match = declare_re.match(trimmed)
            if decl_match:
                module.add_declaration(decl_match.group(2))
                continue
                
            def_match = define_re.match(trimmed)
            if def_match:
                in_function = True
                ret_type = def_match.group(1)
                func_name = def_match.group(2)
                args = def_match.group(3)
                
                current_func = Function(func_name, ret_type, args)
                # First block is block_0 by normalizer design
                current_block = BasicBlock("block_0")
                current_func.add_block(current_block)
                continue
                
            if in_function and trimmed == "}":
                in_function = False
                if current_func:
                    current_func.build_cfg()
                    module.add_function(current_func)
                current_func = None
                current_block = None
                continue
                
            if in_function:
                if trimmed.endswith(":") and trimmed.startswith("block_"):
                    label = trimmed[:-1]
                    current_block = BasicBlock(label)
                    current_func.add_block(current_block)
                else:
                    inst = Instruction(trimmed)
                    if current_block:
                        current_block.add_instruction(inst)
                        
        return module
