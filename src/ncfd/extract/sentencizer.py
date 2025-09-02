"""
Advanced Sentence Splitting with Character Offsets

Provides robust sentence splitting using spaCy/SciSpaCy with accurate character offsets.
Fixes the drift issue in regex-based sentence splitting.
"""

import re
import logging
from typing import List, Tuple, Optional
from dataclasses import dataclass

try:
    import spacy
    from spacy.tokens import Doc
    SPACY_AVAILABLE = True
except ImportError:
    SPACY_AVAILABLE = False
    logging.warning("spaCy not available, falling back to regex-based splitting")

logger = logging.getLogger(__name__)


@dataclass
class SentenceSpan:
    """Represents a sentence with its character offsets."""
    text: str
    start_char: int
    end_char: int
    cleaned_text: str


class AdvancedSentencizer:
    """
    Advanced sentence splitter that provides accurate character offsets.
    
    Uses spaCy/SciSpaCy when available, falls back to improved regex-based splitting.
    """
    
    def __init__(self, use_scispacy: bool = True, fallback_to_regex: bool = True):
        """
        Initialize the sentencizer.
        
        Args:
            use_scispacy: Whether to use SciSpaCy (biomedical model) if available
            fallback_to_regex: Whether to fall back to regex if spaCy is not available
        """
        self.use_scispacy = use_scispacy and SPACY_AVAILABLE
        self.fallback_to_regex = fallback_to_regex
        self.nlp = None
        
        if self.use_scispacy:
            self._initialize_scispacy()
        elif SPACY_AVAILABLE:
            self._initialize_spacy()
        elif not fallback_to_regex:
            raise RuntimeError("spaCy not available and fallback_to_regex=False")
    
    def _initialize_scispacy(self):
        """Initialize SciSpaCy with biomedical model."""
        try:
            # Try to load SciSpaCy model
            self.nlp = spacy.load("en_core_sci_sm")
            logger.info("Loaded SciSpaCy model: en_core_sci_sm")
        except OSError:
            try:
                # Fallback to regular spaCy model
                self.nlp = spacy.load("en_core_web_sm")
                logger.info("Loaded spaCy model: en_core_web_sm (SciSpaCy not available)")
            except OSError:
                logger.warning("No spaCy models available, falling back to regex")
                self.nlp = None
    
    def _initialize_spacy(self):
        """Initialize regular spaCy."""
        try:
            self.nlp = spacy.load("en_core_web_sm")
            logger.info("Loaded spaCy model: en_core_web_sm")
        except OSError:
            logger.warning("No spaCy models available, falling back to regex")
            self.nlp = None
    
    def split_sentences(self, text: str) -> List[SentenceSpan]:
        """
        Split text into sentences with accurate character offsets.
        
        Args:
            text: Input text to split
            
        Returns:
            List of SentenceSpan objects with character offsets
        """
        if self.nlp is not None:
            return self._split_with_spacy(text)
        elif self.fallback_to_regex:
            return self._split_with_regex(text)
        else:
            raise RuntimeError("No sentence splitting method available")
    
    def _split_with_spacy(self, text: str) -> List[SentenceSpan]:
        """Split sentences using spaCy with accurate character offsets."""
        doc = self.nlp(text)
        sentences = []
        
        for sent in doc.sents:
            # Get the exact character offsets from spaCy
            start_char = sent.start_char
            end_char = sent.end_char
            sentence_text = text[start_char:end_char]
            
            # Clean the sentence text and adjust end position to exclude trailing whitespace
            cleaned_text = self._clean_sentence_text(sentence_text)
            if cleaned_text.strip():
                # Adjust end_char to exclude trailing whitespace
                actual_end_char = start_char + len(cleaned_text.rstrip())
                
                sentences.append(SentenceSpan(
                    text=cleaned_text,
                    start_char=start_char,
                    end_char=actual_end_char,
                    cleaned_text=cleaned_text
                ))
        
        return sentences
    
    def _split_with_regex(self, text: str) -> List[SentenceSpan]:
        """
        Split sentences using improved regex with accurate character offsets.
        
        Uses finditer() to get exact start/end positions instead of find().
        """
        sentences = []
        
        # Biomedical sentence splitting pattern
        # Matches sentence endings followed by whitespace and capital letter
        sentence_pattern = r'(?<=[.!?])\s+(?=[A-Z])'
        
        # Find all matches with their positions
        matches = list(re.finditer(sentence_pattern, text))
        
        if not matches:
            # No sentence boundaries found, treat entire text as one sentence
            cleaned_text = self._clean_sentence_text(text)
            if cleaned_text.strip():
                sentences.append(SentenceSpan(
                    text=text,
                    start_char=0,
                    end_char=len(text),
                    cleaned_text=cleaned_text
                ))
            return sentences
        
        # Process sentences between matches
        start_pos = 0
        for match in matches:
            # The match.start() is the position after the sentence ending punctuation
            # We want to include the punctuation in the sentence, so end_pos = match.start()
            end_pos = match.start()  # End of current sentence (including punctuation, excluding whitespace)
            sentence_text = text[start_pos:end_pos]
            
            # Debug output
            print(f"SENTENCIZER DEBUG: start_pos={start_pos}, end_pos={end_pos}, match.start()={match.start()}, match.end()={match.end()}")
            print(f"SENTENCIZER DEBUG: sentence_text='{sentence_text}'")
            
            cleaned_text = self._clean_sentence_text(sentence_text)
            if cleaned_text.strip():
                sentences.append(SentenceSpan(
                    text=sentence_text,
                    start_char=start_pos,
                    end_char=end_pos,
                    cleaned_text=cleaned_text
                ))
            
            start_pos = match.end()  # Start of next sentence (after the whitespace)
        
        # Handle the last sentence (after the last match)
        if start_pos < len(text):
            sentence_text = text[start_pos:]
            cleaned_text = self._clean_sentence_text(sentence_text)
            if cleaned_text.strip():
                sentences.append(SentenceSpan(
                    text=sentence_text,
                    start_char=start_pos,
                    end_char=len(text),
                    cleaned_text=cleaned_text
                ))
        
        return sentences
    
    def _clean_sentence_text(self, text: str) -> str:
        """
        Clean and normalize sentence text.
        
        Args:
            text: Raw sentence text
            
        Returns:
            Cleaned sentence text
        """
        # Remove excessive whitespace
        text = re.sub(r'\s+', ' ', text)
        
        # Remove leading/trailing whitespace
        text = text.strip()
        
        # Remove common sentence artifacts
        text = re.sub(r'^\s*[•\-\*]\s*', '', text)  # Remove bullet points
        text = re.sub(r'^\s*\d+\.\s*', '', text)     # Remove numbered lists
        
        return text
    
    def get_sentence_boundaries(self, text: str) -> List[Tuple[int, int]]:
        """
        Get sentence boundary positions without creating SentenceSpan objects.
        
        Args:
            text: Input text
            
        Returns:
            List of (start_char, end_char) tuples
        """
        sentences = self.split_sentences(text)
        return [(s.start_char, s.end_char) for s in sentences]


# Global sentencizer instance
_global_sentencizer = None


def get_sentencizer() -> AdvancedSentencizer:
    """Get the global sentencizer instance."""
    global _global_sentencizer
    if _global_sentencizer is None:
        _global_sentencizer = AdvancedSentencizer()
    return _global_sentencizer


def split_sentences_with_offsets(text: str) -> List[SentenceSpan]:
    """
    Convenience function to split sentences with character offsets.
    
    Args:
        text: Input text to split
        
    Returns:
        List of SentenceSpan objects
    """
    return get_sentencizer().split_sentences(text)


def get_sentence_boundaries(text: str) -> List[Tuple[int, int]]:
    """
    Convenience function to get sentence boundary positions.
    
    Args:
        text: Input text
        
    Returns:
        List of (start_char, end_char) tuples
    """
    return get_sentencizer().get_sentence_boundaries(text)
