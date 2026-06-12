import re

class Instruction:
    def __init__(self, raw_text):
        self.raw_text = raw_text.strip()
        self.lhs = None
        self.op = None
        self.is_vector = False
        self.is_call = False
        self.called_function = None
        self.parse_instruction()

    def parse_instruction(self):
        # 1. Detect Vector operations or vector types
        # Vector type in LLVM looks like `<4 x i32>` or `<2 x float>`
        # Also opcodes: `shufflevector`, `extractelement`, `insertelement`
        if "<" in self.raw_text and "x" in self.raw_text and ">" in self.raw_text:
            self.is_vector = True
        
        # 2. Extract LHS and rest of the instruction
        # e.g., `%v2 = add nsw i32 %v0, %v1` -> LHS = `%v2`, Rest = `add nsw i32 %v0, %v1`
        if "=" in self.raw_text:
            parts = self.raw_text.split("=", 1)
            self.lhs = parts[0].strip()
            rest = parts[1].strip()
        else:
            self.lhs = None
            rest = self.raw_text

        # 3. Extract opcode
        # Opcode is the first word of the rest string.
        # But we must strip modifiers like `tail`, `musttail`, `notail`, `volatile`, etc.
        words = rest.split()
        if not words:
            self.op = ""
            return
            
        op_idx = 0
        # Skip common instruction modifiers
        modifiers = {"tail", "musttail", "notail", "volatile", "atomic", "weak", "linkonce"}
        while op_idx < len(words) and words[op_idx] in modifiers:
            op_idx += 1
            
        if op_idx < len(words):
            self.op = words[op_idx]
        else:
            self.op = words[0]
            
        # 4. Check if it's a function call and find target
        if self.op == "call":
            self.is_call = True
            # Find the called function which typically starts with `@`
            # e.g., `call i32 @compute(i32 %v1)`
            call_match = re.search(r'@([a-zA-Z0-9._]+)', rest)
            if call_match:
                self.called_function = "@" + call_match.group(1)
                
        # Additional vector check by opcode
        if self.op in ["shufflevector", "extractelement", "insertelement"]:
            self.is_vector = True

    def __repr__(self):
        return f"Instruction({self.lhs} = {self.op} ...)" if self.lhs else f"Instruction({self.op} ...)"


class BasicBlock:
    def __init__(self, label):
        self.label = label
        self.instructions = []
        self.predecessors = set()
        self.successors = []

    def add_instruction(self, inst):
        self.instructions.append(inst)

    def __repr__(self):
        return f"BasicBlock({self.label}, insts={len(self.instructions)}, succs={len(self.successors)})"


class Function:
    def __init__(self, name, return_type, args_section):
        self.name = name
        self.return_type = return_type
        self.args_section = args_section
        self.blocks = {} # label -> BasicBlock
        self.block_order = [] # labels in order of appearance

    def add_block(self, block):
        self.blocks[block.label] = block
        if block.label not in self.block_order:
            self.block_order.append(block.label)

    def build_cfg(self):
        """
        Parses branching and return instructions to connect predecessors and successors
        for all basic blocks in the function.
        """
        # Patterns for branches in normalized IR (block labels are renamed to block_0, block_1 etc.)
        br_cond_re = re.compile(r'br\s+i1\s+[^,]+,\s*label\s+%(block_\d+),\s*label\s+%(block_\d+)')
        br_uncond_re = re.compile(r'br\s+label\s+%(block_\d+)')
        switch_re = re.compile(r'label\s+%(block_\d+)')

        for label in self.block_order:
            block = self.blocks[label]
            if not block.instructions:
                continue
                
            last_inst = block.instructions[-1].raw_text
            
            # 1. Conditional branch
            cond_match = br_cond_re.search(last_inst)
            if cond_match:
                succs = [cond_match.group(1), cond_match.group(2)]
                for s in succs:
                    if s in self.blocks:
                        block.successors.append(s)
                        self.blocks[s].predecessors.add(label)
                continue
                
            # 2. Unconditional branch
            uncond_match = br_uncond_re.search(last_inst)
            if uncond_match:
                succ = uncond_match.group(1)
                if succ in self.blocks:
                    block.successors.append(succ)
                    self.blocks[succ].predecessors.add(label)
                continue
                
            # 3. Switch statement
            if last_inst.startswith("switch "):
                succs = switch_re.findall(last_inst)
                for s in succs:
                    if s in self.blocks:
                        block.successors.append(s)
                        self.blocks[s].predecessors.add(label)
                continue

    def __repr__(self):
        return f"Function({self.name}, blocks={len(self.blocks)})"


class Module:
    def __init__(self):
        self.functions = {} # name -> Function
        self.declarations = set() # set of declared function names

    def add_function(self, func):
        self.functions[func.name] = func

    def add_declaration(self, name):
        self.declarations.add(name)


class IRParser:
    def __init__(self):
        pass

    def parse(self, normalized_ir):
        """
        Parses a normalized LLVM IR text into a Module object.
        """
        module = Module()
        lines = normalized_ir.splitlines()
        
        # Function define: `define <ret_type> @func_name(<args>) ... {`
        # Function declare: `declare <ret_type> @func_name(<args>) ...`
        define_re = re.compile(r'^define\s+(.*?)\s+(@[a-zA-Z0-9._]+)\s*\(([^)]*)\)[^{]*\{')
        declare_re = re.compile(r'^declare\s+(.*?)\s+(@[a-zA-Z0-9._]+)')
        
        in_function = False
        current_func = None
        current_block = None
        
        for line in lines:
            trimmed = line.strip()
            if not trimmed:
                continue
                
            # Check function declaration
            decl_match = declare_re.match(trimmed)
            if decl_match:
                module.add_declaration(decl_match.group(2))
                continue
                
            # Check function start
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
                
            # Check function end
            if in_function and trimmed == "}":
                in_function = False
                if current_block:
                    # Save block if not empty
                    pass
                current_func.build_cfg()
                module.add_function(current_func)
                current_func = None
                current_block = None
                continue
                
            if in_function:
                # Check for basic block label (e.g. `block_1:`)
                if trimmed.endswith(":") and trimmed.startswith("block_"):
                    label = trimmed[:-1]
                    current_block = BasicBlock(label)
                    current_func.add_block(current_block)
                else:
                    # It's an instruction
                    inst = Instruction(trimmed)
                    if current_block:
                        current_block.add_instruction(inst)
                        
        return module

if __name__ == "__main__":
    from normalizer import IRNormalizer
    
    sample_ir = """
define i32 @test(i32 %arg1, i32 %arg2) {
block_0:
  %v0 = icmp sgt i32 %v1, %v2
  br i1 %v0, label %block_1, label %block_2

block_1:
  %v3 = add nsw i32 %v1, 10
  br label %block_3

block_2:
  %v4 = sub nsw i32 %v2, 5
  br label %block_3

block_3:
  %v5 = phi i32 [ %v3, %block_1 ], [ %v4, %block_2 ]
  ret i32 %v5
}
"""
    parser = IRParser()
    m = parser.parse(sample_ir)
    print(m.functions)
    func = m.functions["@test"]
    print("Blocks:", func.blocks)
    print("CFG block_0 succs:", func.blocks["block_0"].successors)
    print("CFG block_3 preds:", func.blocks["block_3"].predecessors)
