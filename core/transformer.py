import re
from .models import CaseStyle


class NameTransformer:
    """Transform names into different case styles."""
    
    def transform(self, name: str, style: CaseStyle) -> str:
        """
        Transform a name into the specified case style.
        
        Args:
            name: Input name (any format)
            style: Target case style
            
        Returns:
            Transformed name
        """
        # First, split the name into words
        words = self._split_into_words(name)
        
        if not words:
            return name
        
        # Apply the transformation
        transformers = {
            CaseStyle.CAMEL: self._to_camel_case,
            CaseStyle.CAPITAL: self._to_capital_case,
            CaseStyle.CONSTANT: self._to_constant_case,
            CaseStyle.DOT: self._to_dot_case,
            CaseStyle.KEBAB: self._to_kebab_case,
            CaseStyle.NO: self._to_no_case,
            CaseStyle.PASCAL: self._to_pascal_case,
            CaseStyle.PASCAL_SNAKE: self._to_pascal_snake_case,
            CaseStyle.PATH: self._to_path_case,
            CaseStyle.SENTENCE: self._to_sentence_case,
            CaseStyle.SNAKE: self._to_snake_case,
            CaseStyle.TRAIN: self._to_train_case,
        }
        
        transformer = transformers.get(style, self._to_kebab_case)
        return transformer(words)
    
    def _split_into_words(self, name: str) -> list[str]:
        """
        Split a name into individual words.
        
        Handles:
        - camelCase -> ["camel", "Case"]
        - snake_case -> ["snake", "case"]
        - kebab-case -> ["kebab", "case"]
        - dot.case -> ["dot", "case"]
        - Mixed formats
        """
        # Replace common separators with spaces
        s = re.sub(r'[-_./\\]', ' ', name)
        
        # Insert space before uppercase letters (for camelCase)
        s = re.sub(r'([a-z])([A-Z])', r'\1 \2', s)
        
        # Insert space between letters and numbers
        s = re.sub(r'([a-zA-Z])(\d)', r'\1 \2', s)
        s = re.sub(r'(\d)([a-zA-Z])', r'\1 \2', s)
        
        # Split and filter
        words = [w.strip() for w in s.split() if w.strip()]
        
        return words
    
    # ─────────────────────────────────────────────────────────────────────────
    # Transformation Methods
    # ─────────────────────────────────────────────────────────────────────────
    
    def _to_camel_case(self, words: list[str]) -> str:
        """camelCase: first word lowercase, rest capitalized."""
        if not words:
            return ""
        result = words[0].lower()
        for word in words[1:]:
            result += word.capitalize()
        return result
    
    def _to_capital_case(self, words: list[str]) -> str:
        """Capital Case: each word capitalized, space separated."""
        return " ".join(word.capitalize() for word in words)
    
    def _to_constant_case(self, words: list[str]) -> str:
        """CONSTANT_CASE: all uppercase, underscore separated."""
        return "_".join(word.upper() for word in words)
    
    def _to_dot_case(self, words: list[str]) -> str:
        """dot.case: all lowercase, dot separated."""
        return ".".join(word.lower() for word in words)
    
    def _to_kebab_case(self, words: list[str]) -> str:
        """kebab-case: all lowercase, hyphen separated."""
        return "-".join(word.lower() for word in words)
    
    def _to_no_case(self, words: list[str]) -> str:
        """no case: all lowercase, space separated."""
        return " ".join(word.lower() for word in words)
    
    def _to_pascal_case(self, words: list[str]) -> str:
        """PascalCase: each word capitalized, no separator."""
        return "".join(word.capitalize() for word in words)
    
    def _to_pascal_snake_case(self, words: list[str]) -> str:
        """Pascal_Snake_Case: each word capitalized, underscore separated."""
        return "_".join(word.capitalize() for word in words)
    
    def _to_path_case(self, words: list[str]) -> str:
        """path/case: all lowercase, slash separated."""
        return "/".join(word.lower() for word in words)
    
    def _to_sentence_case(self, words: list[str]) -> str:
        """Sentence case: first word capitalized, rest lowercase, space separated."""
        if not words:
            return ""
        result = words[0].capitalize()
        if len(words) > 1:
            result += " " + " ".join(word.lower() for word in words[1:])
        return result
    
    def _to_snake_case(self, words: list[str]) -> str:
        """snake_case: all lowercase, underscore separated."""
        return "_".join(word.lower() for word in words)
    
    def _to_train_case(self, words: list[str]) -> str:
        """Train-Case: each word capitalized, hyphen separated."""
        return "-".join(word.capitalize() for word in words)