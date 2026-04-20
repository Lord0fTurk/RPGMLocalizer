from __future__ import annotations
from lark import Lark
from typing import List, Tuple, Any
import logging

# --- RPG Maker Grammar ---
# Bu gramer, metin içindeki kodları (command) ve düz metni (text) 
# birbirine karıştırmadan ayırt etmek için tasarlanmıştır.
RPG_LEXER_GRAMMAR = r"""
    start: (CODE | TEXT)+
    
    # 1. Protected System Tags/Codes
    # ⟦⟧ tokens (U+27E6/U+27E7): translation-engine-safe placeholders & separators
    # Both uppercase and lowercase escape sequences are matched (e.g. \C[n] and \c[n]).
    CODE.2: /\\(?:[A-Za-z]+(?:\[(?:[0-9]+|"[^"]+")\])?|[\.\^\|\!><\{\}\$])|⟦[0-9A-Za-z_]+⟧|<[^>]+>|[\uE000-\uE003]/
          | /【\s*_[SMI]_\s*】/i
          | /\{[\/]?[a-z0-9]+\}/i
          | /〈[^〉\n]+〉/
          | /\|{3}[^|\n]+\|{3}/

    TEXT: /.+?/s
"""

class StringSegment:
    def __init__(self, content: str, is_code: bool):
        self.content = content
        self.is_code = is_code

    def __repr__(self):
        type_str = "CODE" if self.is_code else "TEXT"
        return f"[{type_str}: {self.content}]"

class RPGLexer:
    def __init__(self):
        self.logger = logging.getLogger("RPGLexer")
        # Direct lexing
        self.parser = Lark(RPG_LEXER_GRAMMAR, start='start', parser='earley')

    def tokenize(self, text: str) -> List[StringSegment]:
        if not text: return []
        try:
            tree = self.parser.parse(text)
            segments = []
            
            for token in tree.children:
                kind = token.type
                content = str(token)
                
                is_code = (kind == 'CODE')
                
                if not is_code and segments and not segments[-1].is_code:
                    segments[-1].content += content
                else:
                    segments.append(StringSegment(content, is_code=is_code))
            
            return segments
        except Exception as e:
            self.logger.warning(f"Lexer fail: {e}")
            return [StringSegment(text, is_code=False)]

# Test bolumu
if __name__ == "__main__":
    lexer = RPGLexer()
    test_str = "Merhaba \\C[1]Kahraman\\C[0]! <WordWrap> [name] hoscakal."
    tokens = lexer.tokenize(test_str)
    for t in tokens:
        print(t)
