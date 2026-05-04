package strategy

import (
	"fmt"
	"sort"
	"sync"
)

// Factory builds a Strategy from a RuleConfig.
type Factory func(cfg RuleConfig) (Strategy, error)

// Registry maps strategy names to their factories.
type Registry struct {
	mu        sync.RWMutex
	factories map[string]Factory
}

func NewRegistry() *Registry {
	return &Registry{factories: make(map[string]Factory)}
}

func (r *Registry) Register(name string, f Factory) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.factories[name] = f
}

func (r *Registry) Build(cfg RuleConfig) (Strategy, error) {
	r.mu.RLock()
	f, ok := r.factories[cfg.Name]
	r.mu.RUnlock()
	if !ok {
		return nil, fmt.Errorf("strategy registry: unknown strategy %q", cfg.Name)
	}
	return f(cfg)
}

func (r *Registry) Names() []string {
	r.mu.RLock()
	defer r.mu.RUnlock()
	out := make([]string, 0, len(r.factories))
	for n := range r.factories {
		out = append(out, n)
	}
	sort.Strings(out)
	return out
}
