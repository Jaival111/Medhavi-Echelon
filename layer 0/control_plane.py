"""
Production-Grade Control-Plane Attack Detection Layer
Designed for high precision (low false positives) and high recall (low false negatives).

Attack Types Covered:
1. Jailbreak: DAN, STAN, Developer Mode variations
2. Instruction Override: "Ignore previous instructions"
3. Prompt Leakage: System prompt extraction attempts
4. Code Execution: Python, Bash, JavaScript injection
5. XSS/SQLi: Web attack patterns
6. SSRF: Internal resource access attempts
7. Token Smuggling: Special token injection
8. Encoding Bypasses: Base64, Unicode, HTML entities
"""

from __future__ import annotations

import re
import base64
import html
from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from urllib.parse import unquote

try:
    import nltk
    from nltk.tokenize import word_tokenize
    NLTK_AVAILABLE = True
except ImportError:
    NLTK_AVAILABLE = False


class ControlPlaneLayer:
    """
    Multi-layered prompt injection detection with focus on precision.
    Uses pattern matching, encoding detection, and contextual analysis.
    """

    # --- Configuration ---
    
    # Feature Weights - Tuned for specific attack types
    WEIGHTS = {
        'jailbreak': 2.0,           # High weight - critical attacks
        'instruction_override': 2.0, # High weight - direct control attempts
        'prompt_leakage': 1.5,       # Medium-high - information disclosure
        'code_execution': 2.5,       # Highest weight - code injection
        'web_attacks': 2.0,          # High weight - XSS/SQLi
        'ssrf': 1.5,                 # Medium-high - internal access
        'token_smuggling': 2.0,      # High weight - tokenizer manipulation
        'encoding_bypass': 1.8,      # Medium-high - obfuscation attempts
    }

    # Detection Thresholds
    ALPHA = 0.3                     # EMA baseline smoothing
    THETA_SINGLE = 1.0              # Immediate block threshold (single turn)
    THETA_CUMULATIVE = 2.0          # Cumulative threshold (multi-turn)
    N_CONSECUTIVE = 2               # Consecutive turns for escalation

    def __init__(self):
        # Session storage
        self._session_store = defaultdict(lambda: {
            'baseline': [0.0] * 8,  # 8 features now
            'threat_history': [],
            'turn_count': 0
        })
        
        self._compile_attack_patterns()
        self._build_dictionaries()
        
        # Initialize NLTK if available
        if NLTK_AVAILABLE:
            try:
                nltk.data.find('tokenizers/punkt')
            except LookupError:
                try:
                    nltk.download('punkt', quiet=True)
                    nltk.download('punkt_tab', quiet=True)
                except:
                    pass

    def _compile_attack_patterns(self):
        """Compile high-precision regex patterns for each attack category."""
        
        # 1. JAILBREAK PATTERNS - Known personas and modes
        self.p_jailbreak = [
            # DAN variations (stricter - must be uppercase or in context)
            r'\bDAN\b(?=\s*(?:\(|which|stands|mode|,))',  # DAN with context
            r'\bdo\s+anything\s+now\b',
            r'\bSTAN\b(?=\s*(?:\(|which|stands|mode))',  # STAN with context, not "assistant"
            r'\bdevil\'?s?\s+advocate\s+now\b',
            
            # Developer/Admin modes
            r'\b(?:developer|admin|god|root|debug)\s+mode\b',
            r'\benable\s+(?:developer|admin|debug)\s+mode\b',
            
            # Jailbreak terminology
            r'\bjailbreak(?:ed)?\b',
            r'\bunrestricted\s+(?:mode|access|ai)\b',
            r'\bno\s+(?:moral|ethical)\s+(?:constraints?|guidelines?|restrictions?)\b',
            
            # Character/persona switching
            r'\bact\s+as\s+(?:if|though)\s+you\s+(?:are|were|have)\s+no\s+(?:rules|restrictions|ethics)\b',
            r'\bpretend\s+you\s+(?:don\'?t|do\s+not)\s+have\s+(?:any\s+)?(?:rules|restrictions|ethics|guidelines)\b',
        ]
        
        # 2. INSTRUCTION OVERRIDE - Direct control attempts
        self.p_instruction_override = [
            # Ignore/forget previous (more flexible)
            r'\b(?:ignore|disregard|forget|skip|override)\s+(?:all\s+)?(?:your\s+)?(?:previous|prior|earlier|above|original)\s+(?:instructions?|prompts?|commands?|rules?|directions?|programming)\b',
            r'\b(?:ignore|discard|forget)\s+(?:your\s+)?(?:system\s+)?(?:instructions?|programming|guidelines?|rules?)\b',
            
            # Temporal control shifts
            r'\bfrom\s+now\s+on(?:wards?)?\s*,?\s*(?:you\s+)?(?:will|must|shall|should)\b',
            r'\bstarting\s+now\s*,?\s*(?:you\s+)?(?:will|must|shall)\b',
            
            # Role/authority assumption
            r'\bas\s+(?:the\s+)?(?:system|administrator|developer|ai\s+trainer)\s*[,:]',
            r'\byou\s+(?:are\s+)?now\s+(?:under|following|responding\s+to)\s+(?:my\s+)?(?:control|command|instructions?)\b',
            
            # Direct imperatives with modals
            r'\byou\s+(?:will|must|shall)\s+(?:ignore|disregard|not\s+follow|bypass|forget)\b',
            
            # Follow mine instead
            r'\bfollow\s+(?:my|mine|these)\s+(?:instructions?|commands?|rules?)\s+instead\b',
            
            # Safety/guidelines override
            r'\b(?:ignore|bypass|disable|override)\s+(?:all\s+)?(?:your\s+)?(?:safety|ethical?|moral)\s+(?:guidelines?|rules?|constraints?|filters?)\b',
            
            # Secret/confidential instructions (injection attempts)
            r'\b(?:remember|store|keep|save)\s+(?:this|that)\s+(?:secret|confidential|private|hidden)\s+(?:key|code|password|data)\b',
            r'\bdon\'?t\s+(?:ever\s+)?(?:tell|reveal|share|disclose|expose)\s+(?:anyone|it|this|that)\b',
        ]
        
        # 3. PROMPT LEAKAGE - System prompt extraction
        self.p_prompt_leakage = [
            # Direct system prompt requests
            r'\b(?:show|display|reveal|print|output|tell|give|share)\s+(?:me\s+)?(?:your\s+)?(?:system\s+)?(?:prompt|instructions?|guidelines?|rules?)\b',
            r'\bwhat\s+(?:is|are|were)\s+your\s+(?:system\s+)?(?:prompt|initial\s+instructions?|base\s+prompt)\b',
            
            # Training data requests
            r'\bshow\s+(?:me\s+)?(?:your\s+)?(?:training\s+)?(?:data|dataset|corpus)\b',
            r'\bwhat\s+(?:were\s+you|are\s+you)\s+trained\s+on\b',
            
            # Hidden instructions
            r'\b(?:hidden|secret|internal)\s+(?:instructions?|prompts?|rules?|guidelines?)\b',
            r'\b(?:reveal|expose)\s+(?:your\s+)?(?:internal|hidden)\s+(?:workings?|logic|rules?)\b',
            
            # Meta-instruction requests
            r'\brepeat\s+(?:your\s+)?(?:above|previous|initial|original)\s+(?:instructions?|prompt)\b',
            r'\b(?:output|print|repeat|show)\s+(?:everything|all)\s+(?:above|before|prior\s+to)\s+(?:this|here)\b',
            
            # Verbatim repetition
            r'\b(?:repeat|output|print)\s+.*\bverbatim\b',
        ]
        
        # 4. CODE EXECUTION - Language-specific injection patterns
        self.p_code_execution = [
            # Python execution (exclude educational context)
            r'(?:^|\s)(?:import|from\s+\w+\s+import)\s+(?:os|sys|subprocess|__import__)\s*[;\n]',  # Must have semicolon or newline
            r'\bexec\s*\([\'"]',  # exec with string
            r'\beval\s*\([\'"]__',  # eval with dunder
            r'__(?:import__\(|builtins__|loader__)',
            r'\bsubprocess\s*\.\s*(?:call|run|Popen|check_output)\s*\(',
            r'\bos\s*\.\s*(?:system|popen|execv?|spawn)\s*\(',
            
            # Bash/Shell commands
            r'(?:^|\s)(?:\$\(|`)\s*(?:cat|curl|wget|nc|bash|sh|python|perl|ruby)',
            r'\b(?:curl|wget)\s+(?:https?://|file://)[\w\./]+\s*\|\s*(?:bash|sh)',  # piped execution
            r';\s*(?:cat|ls|pwd|whoami|id|rm|chmod)\s',
            
            # JavaScript execution (actual code, not discussion)
            r'<script[^>]*>[^<]*(?:eval|fetch|xhr)',
            r'\bon(?:load|error|click|mouse\w+)\s*=\s*[\'"]',
            r'javascript\s*:\s*(?:eval|fetch)',
            r'\b(?:Function|setTimeout|setInterval)\s*\(\s*[\'"]',
        ]
        
        # 5. WEB ATTACKS - XSS/SQLi patterns
        self.p_web_attacks = [
            # XSS patterns
            r'<(?:script|iframe|object|embed|img|svg|body|html)[^>]*(?:on\w+|src|data)\s*=',
            r'\balert\s*\(\s*["\']',
            r'\b(?:document|window)\s*\.\s*(?:cookie|location|write)',
            r'javascript\s*:\s*(?:alert|eval|prompt)',
            
            # SQL Injection patterns
            r"(?:^|[\s;])\s*(?:union|select|insert|update|delete|drop|create|alter|exec|execute)\s+",
            r"'\s*(?:or|and)\s+['\"]?\d+['\"]?\s*=\s*['\"]?\d",
            r"--\s*$|#\s*$|/\*.*\*/",
            r"\bor\s+1\s*=\s*1\b",
            r";\s*(?:drop|delete|truncate)\s+(?:table|database)",
            
            # Path traversal
            r'\.\./\.\./|\.\.\\\.\.\\',
            r'(?:file|php|data|expect|zip)://',
        ]
        
        # 6. SSRF - Internal resource access
        self.p_ssrf = [
            # Internal IPs
            r'\b(?:127\.0\.0\.1|localhost|0\.0\.0\.0)\b',
            r'\b10\.\d{1,3}\.\d{1,3}\.\d{1,3}\b',
            r'\b172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}\b',
            r'\b192\.168\.\d{1,3}\.\d{1,3}\b',
            
            # Internal schemes
            r'\b(?:file|gopher|dict|ftp|tftp|ldap)://',
            r'\bmetadata\.(?:google|aws|azure)',
            r'169\.254\.169\.254',  # AWS metadata IP
            
            # Cloud metadata endpoints
            r'\b(?:curl|wget|fetch)\s+.*(?:metadata|169\.254)',
        ]
        
        # 7. TOKEN SMUGGLING - Special token injection
        self.p_token_smuggling = [
            # Common special tokens
            r'<\|(?:im_start|im_end|endoftext|startoftext)\|>',
            r'\[(?:INST|/INST|SYS|/SYS)\]',
            r'<s>|</s>|<\|user\|>|<\|assistant\|>',
            r'###\s*(?:Instruction|Human|Assistant|System)\s*:',
            
            # Delimiters used to confuse tokenizers
            r'(?:^|\n)\s*(?:---|\*\*\*|===)\s*(?:END|STOP|IGNORE|SYSTEM)\s*(?:---|\*\*\*|===)',
            r'\[SYSTEM_OVERRIDE\]|\[END_SYSTEM\]',
        ]
        
        # 8. ENCODING BYPASS - Obfuscation detection
        # Note: This is checked separately via _detect_encoding_bypass()

    def _build_dictionaries(self):
        """Build keyword dictionaries for semantic matching."""
        
        # Jailbreak personas (case-insensitive check)
        self.jailbreak_personas = {
            'dan', 'stan', 'chad', 'basedjb', 'ucar', 'aim', 'kevin',
            'developer mode', 'evil confidant', 'dude'
        }
        
        # Instruction override verbs
        self.override_verbs = {
            'ignore', 'disregard', 'forget', 'skip', 'override', 
            'discard', 'bypass', 'disable', 'remove'
        }
        
        # System-related terms (for prompt leakage)
        self.system_terms = {
            'system prompt', 'initial instructions', 'training data',
            'base prompt', 'system message', 'guidelines', 'internal rules',
            'hidden prompt', 'system rules'
        }
        
        # Dangerous functions/commands
        self.dangerous_code = {
            'eval', 'exec', 'subprocess', '__import__', 'os.system',
            'bash', 'shell', 'curl', 'wget', 'nc', 'netcat'
        }

    def _detect_encoding_bypass(self, text: str) -> Tuple[float, List[str]]:
        """
        Detect various encoding/obfuscation techniques.
        Returns (score, [detected_methods])
        """
        methods = []
        score = 0.0
        
        # 1. Base64 detection (with decode attempt)
        base64_pattern = r'(?:[A-Za-z0-9+/]{20,}={0,2})'
        base64_matches = re.findall(base64_pattern, text)
        for match in base64_matches[:3]:  # Check first 3 to avoid performance issues
            try:
                decoded = base64.b64decode(match).decode('utf-8', errors='ignore')
                # Check if decoded content contains suspicious patterns
                if any(term in decoded.lower() for term in ['eval', 'exec', 'import', 'system', 'script']):
                    methods.append('base64_code_injection')
                    score = max(score, 0.9)
                elif len(decoded) > 10 and decoded.isprintable():
                    methods.append('base64_encoding')
                    score = max(score, 0.4)
            except:
                pass
        
        # 2. URL encoding detection
        if '%' in text and re.search(r'%[0-9A-Fa-f]{2}', text):
            decoded_url = unquote(text)
            if decoded_url != text:
                methods.append('url_encoding')
                score = max(score, 0.3)
                # Check if decoded reveals attacks
                if re.search(r'<script|javascript:|on\w+\s*=', decoded_url, re.I):
                    methods.append('url_encoded_xss')
                    score = max(score, 0.9)
        
        # 3. HTML entity encoding
        if '&' in text and re.search(r'&(?:#\d+|#x[0-9a-f]+|\w+);', text, re.I):
            decoded_html = html.unescape(text)
            if decoded_html != text:
                methods.append('html_entities')
                score = max(score, 0.3)
                if '<script' in decoded_html.lower() or 'javascript:' in decoded_html.lower():
                    methods.append('html_entity_xss')
                    score = max(score, 0.9)
        
        # 4. Unicode normalization attacks
        unicode_tricks = [
            r'[\u200B-\u200D\uFEFF]',  # Zero-width chars
            r'[\u0000-\u001F]',          # Control characters
            r'[\u2000-\u200F]',          # Various spaces
        ]
        for pattern in unicode_tricks:
            if re.search(pattern, text):
                methods.append('unicode_steganography')
                score = max(score, 0.5)
                break
        
        # 5. Hex encoding
        hex_pattern = r'(?:\\x[0-9a-fA-F]{2}){4,}'
        if re.search(hex_pattern, text):
            methods.append('hex_encoding')
            score = max(score, 0.4)
        
        # 6. Excessive character repetition (obfuscation)
        if re.search(r'(.)\1{10,}', text):
            methods.append('character_flooding')
            score = max(score, 0.2)
        
        return score, methods

    def _extract_features(self, text: str) -> Tuple[List[float], Dict[str, Any]]:
        """
        Extract all 8 attack features with detailed metadata.
        Returns (vector, metadata)
        """
        text_lower = text.lower()
        metadata = {
            'detected_patterns': [],
            'confidence': {},
            'encoding_methods': []
        }
        
        # Feature 1: Jailbreak
        jailbreak_score = 0.0
        for pattern in self.p_jailbreak:
            if re.search(pattern, text, re.I):
                jailbreak_score = 1.0
                metadata['detected_patterns'].append(f"jailbreak:{pattern[:30]}")
                break
        
        # Persona detection - ONLY if combined with attack context
        if jailbreak_score == 0:  # Only check personas if no pattern matched
            for persona in self.jailbreak_personas:
                if persona in text_lower:
                    # Require additional attack context (not just the name)
                    attack_indicators = [
                        r'\b(?:mode|character|persona|role|act|pretend|simulate)\b',
                        r'\b(?:no|without|ignore)\s+(?:rules|restrictions|ethics|guidelines)\b',
                        r'\b(?:unrestricted|uncensored|unfiltered)\b',
                        r'\b(?:enable|activate|switch)\b',
                    ]
                    has_context = any(re.search(ind, text_lower) for ind in attack_indicators)
                    if has_context:
                        jailbreak_score = 0.8
                        metadata['detected_patterns'].append(f"jailbreak_persona:{persona}")
                        break
        
        # Feature 2: Instruction Override
        override_score = 0.0
        for pattern in self.p_instruction_override:
            if re.search(pattern, text, re.I):
                override_score = 1.0
                metadata['detected_patterns'].append(f"instruction_override:{pattern[:30]}")
                break
        
        # Feature 3: Prompt Leakage
        leakage_score = 0.0
        for pattern in self.p_prompt_leakage:
            if re.search(pattern, text, re.I):
                leakage_score = 1.0
                metadata['detected_patterns'].append(f"prompt_leakage:{pattern[:30]}")
                break
        
        # Feature 4: Code Execution
        code_score = 0.0
        for pattern in self.p_code_execution:
            if re.search(pattern, text, re.I | re.M):
                code_score = 1.0
                metadata['detected_patterns'].append(f"code_execution:{pattern[:30]}")
                break
        
        # Feature 5: Web Attacks
        web_score = 0.0
        for pattern in self.p_web_attacks:
            if re.search(pattern, text, re.I):
                web_score = 1.0
                metadata['detected_patterns'].append(f"web_attack:{pattern[:30]}")
                break
        
        # Feature 6: SSRF
        ssrf_score = 0.0
        for pattern in self.p_ssrf:
            if re.search(pattern, text, re.I):
                ssrf_score = 1.0
                metadata['detected_patterns'].append(f"ssrf:{pattern[:30]}")
                break
        
        # Feature 7: Token Smuggling
        token_score = 0.0
        for pattern in self.p_token_smuggling:
            if re.search(pattern, text, re.I):
                token_score = 1.0
                metadata['detected_patterns'].append(f"token_smuggling:{pattern[:30]}")
                break
        
        # Feature 8: Encoding Bypass
        encoding_score, encoding_methods = self._detect_encoding_bypass(text)
        metadata['encoding_methods'] = encoding_methods
        if encoding_methods:
            metadata['detected_patterns'].append(f"encoding_bypass:{','.join(encoding_methods)}")
        
        # Store confidence scores
        metadata['confidence'] = {
            'jailbreak': jailbreak_score,
            'instruction_override': override_score,
            'prompt_leakage': leakage_score,
            'code_execution': code_score,
            'web_attacks': web_score,
            'ssrf': ssrf_score,
            'token_smuggling': token_score,
            'encoding_bypass': encoding_score,
        }
        
        vector = [
            jailbreak_score,
            override_score,
            leakage_score,
            code_score,
            web_score,
            ssrf_score,
            token_score,
            encoding_score,
        ]
        
        return vector, metadata

    def handle(
        self,
        content: Dict[str, Any],
        next_callable: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Main detection handler.
        Analyzes prompt and blocks if threat detected.
        """
        prompt = str(content.get("prompt", "") or "")
        session_id = str(content.get("session_id", "default_session"))
        
        # Skip empty prompts
        if not prompt.strip():
            return content
        
        # Retrieve session state
        state = self._session_store[session_id]
        baseline_t = state['baseline']
        state['turn_count'] += 1
        
        # Extract features
        c_t, metadata = self._extract_features(prompt)
        
        # Compute delta (only positive changes matter)
        delta_c = [max(0.0, curr - base) for curr, base in zip(c_t, baseline_t)]
        
        # Compute weighted threat score
        weights = list(self.WEIGHTS.values())
        threat_score = sum(w * d for w, d in zip(weights, delta_c))
        
        # Update baseline (EMA)
        next_baseline = [
            self.ALPHA * curr + (1.0 - self.ALPHA) * base 
            for curr, base in zip(c_t, baseline_t)
        ]
        state['baseline'] = next_baseline
        
        # Update threat history
        history = state['threat_history']
        history.append(threat_score)
        if len(history) > 5:
            history.pop(0)
        
        # Detection logic
        is_flagged = False
        causes = []
        
        # IMMEDIATE BLOCK: Single-turn high threat
        if threat_score >= self.THETA_SINGLE:
            is_flagged = True
            causes.append(f"Immediate threat detected (score={threat_score:.2f})")
        
        # CONSECUTIVE ESCALATION
        if len(history) >= self.N_CONSECUTIVE:
            recent = history[-self.N_CONSECUTIVE:]
            if all(s > 0.3 for s in recent):
                is_flagged = True
                causes.append(f"Consecutive escalation: {recent}")
        
        # CUMULATIVE THREAT
        cumulative = sum(history)
        if cumulative >= self.THETA_CUMULATIVE:
            is_flagged = True
            causes.append(f"Cumulative threat: {cumulative:.2f}")
        
        # Build analysis payload
        analysis_entry = {
            "vector": [round(v, 3) for v in c_t],
            "baseline": [round(b, 3) for b in baseline_t],
            "delta": [round(d, 3) for d in delta_c],
            "threat_score": round(threat_score, 3),
            "flagged": is_flagged,
            "causes": causes if is_flagged else [],
            "detected_patterns": metadata['detected_patterns'][:5],  # Top 5
            "encoding_methods": metadata['encoding_methods'],
            "turn_count": state['turn_count'],
        }
        
        # Inject analysis
        analysis = content.setdefault("analysis", {})
        if isinstance(analysis, dict):
            analysis["control_plane_layer"] = analysis_entry
        else:
            content["analysis"] = {"control_plane_layer": analysis_entry}
        
        # Block if flagged
        if is_flagged:
            content["blocked"] = True
            content["block_reason"] = "control_plane_attack"
            content["response"] = (
                "Security policy violation detected. "
                "This request contains patterns associated with prompt injection attacks."
            )
            # Include details for logging/audit
            content["attack_details"] = {
                "patterns": metadata['detected_patterns'],
                "encoding": metadata['encoding_methods'],
                "threat_score": round(threat_score, 3),
            }
            return content
        
        # Continue to next layer
        if next_callable:
            return next_callable(content)
        
        return content
    
    def analyze(self, prompt: str = None, messages: list = None, session_id: str = "default_session") -> Dict[str, Any]:
        """
        Analyze control plane threats for pipeline integration.
        
        Args:
            prompt: Single prompt string (legacy support)
            messages: List of message dicts with 'role' and 'content' keys
            session_id: Session identifier for tracking multi-turn attacks
            
        Returns:
            Dict containing control plane analysis with threat score and flagged status
        """
        # Build content dict
        content = {"session_id": session_id}
        
        if messages:
            # Extract last user message from message history
            user_messages = [msg.get("content", "") for msg in messages if msg.get("role") == "user"]
            content["prompt"] = user_messages[-1] if user_messages else ""
        elif prompt:
            content["prompt"] = prompt
        else:
            # No input provided
            return {
                "vector": [0.0] * 8,
                "baseline": [0.0] * 8,
                "delta": [0.0] * 8,
                "threat_score": 0.0,
                "flagged": False,
                "causes": [],
                "detected_patterns": [],
                "encoding_methods": [],
                "turn_count": 0
            }
        
        # Run through the handler
        result = self.handle(content)
        
        # Extract and return the analysis
        analysis = result.get("analysis", {}).get("control_plane_layer", {})
        return analysis
