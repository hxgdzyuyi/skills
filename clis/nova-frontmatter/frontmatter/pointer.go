package frontmatter

import (
	"fmt"
	"strconv"
	"strings"
)

type Operation string

const (
	OpReplace Operation = "replace"
	OpAdd     Operation = "add"
	OpRemove  Operation = "remove"
)

// ParsePointer parses a JSON Pointer (RFC 6901) string into reference tokens.
func ParsePointer(ptr string) ([]string, error) {
	if ptr == "" {
		return []string{}, nil
	}
	if !strings.HasPrefix(ptr, "/") {
		return nil, fmt.Errorf("invalid JSON Pointer: must start with /")
	}
	raw := strings.Split(ptr[1:], "/")
	tokens := make([]string, len(raw))
	for i, t := range raw {
		// RFC 6901: ~1 decodes to /, ~0 decodes to ~
		// Order matters: decode ~1 first, then ~0
		t = strings.ReplaceAll(t, "~1", "/")
		t = strings.ReplaceAll(t, "~0", "~")
		tokens[i] = t
	}
	return tokens, nil
}

// PointerGet navigates the data structure and returns the value at the given path.
func PointerGet(data interface{}, tokens []string) (interface{}, error) {
	current := data
	for _, token := range tokens {
		switch v := current.(type) {
		case map[string]interface{}:
			val, ok := v[token]
			if !ok {
				return nil, fmt.Errorf("key %q not found", token)
			}
			current = val
		case []interface{}:
			idx, err := strconv.Atoi(token)
			if err != nil {
				return nil, fmt.Errorf("invalid array index %q", token)
			}
			if idx < 0 || idx >= len(v) {
				return nil, fmt.Errorf("array index %d out of bounds (length %d)", idx, len(v))
			}
			current = v[idx]
		default:
			return nil, fmt.Errorf("cannot navigate into %T with token %q", current, token)
		}
	}
	return current, nil
}

// PointerApply applies an operation (replace/add/remove) at the given path.
// Returns the (potentially new) data root, since array operations may replace the container.
func PointerApply(data interface{}, tokens []string, op Operation, value interface{}, createMissing bool) (interface{}, error) {
	if len(tokens) == 0 {
		if op == OpReplace {
			return value, nil
		}
		return nil, fmt.Errorf("cannot %s root document", op)
	}

	token := tokens[0]
	rest := tokens[1:]

	switch v := data.(type) {
	case map[string]interface{}:
		if len(rest) == 0 {
			switch op {
			case OpReplace:
				if _, ok := v[token]; !ok && !createMissing {
					return nil, fmt.Errorf("key %q not found", token)
				}
				v[token] = value
			case OpAdd:
				v[token] = value
			case OpRemove:
				if _, ok := v[token]; !ok {
					return nil, fmt.Errorf("key %q not found", token)
				}
				delete(v, token)
			}
			return data, nil
		}

		child, ok := v[token]
		if !ok {
			if createMissing {
				child = make(map[string]interface{})
				v[token] = child
			} else {
				return nil, fmt.Errorf("key %q not found", token)
			}
		}
		result, err := PointerApply(child, rest, op, value, createMissing)
		if err != nil {
			return nil, err
		}
		v[token] = result
		return data, nil

	case []interface{}:
		// "-" means append (only valid for add at terminal position)
		if token == "-" && len(rest) == 0 && op == OpAdd {
			return append(v, value), nil
		}

		idx, err := strconv.Atoi(token)
		if err != nil {
			return nil, fmt.Errorf("invalid array index %q", token)
		}

		if op == OpAdd && len(rest) == 0 {
			if idx < 0 || idx > len(v) {
				return nil, fmt.Errorf("array index %d out of bounds for insert (length %d)", idx, len(v))
			}
			result := make([]interface{}, len(v)+1)
			copy(result, v[:idx])
			result[idx] = value
			copy(result[idx+1:], v[idx:])
			return result, nil
		}

		if idx < 0 || idx >= len(v) {
			return nil, fmt.Errorf("array index %d out of bounds (length %d)", idx, len(v))
		}

		if len(rest) == 0 {
			switch op {
			case OpReplace:
				v[idx] = value
				return v, nil
			case OpRemove:
				return append(v[:idx], v[idx+1:]...), nil
			}
		}

		childResult, err := PointerApply(v[idx], rest, op, value, createMissing)
		if err != nil {
			return nil, err
		}
		v[idx] = childResult
		return v, nil

	default:
		if createMissing {
			newMap := make(map[string]interface{})
			return PointerApply(newMap, tokens, op, value, createMissing)
		}
		return nil, fmt.Errorf("cannot navigate into %T with token %q", data, token)
	}
}
