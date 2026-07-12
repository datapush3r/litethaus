interface TabBarProps {
  items: string[]
  active: string | null
  onSelect: (item: string) => void
}

export function TabBar({ items, active, onSelect }: TabBarProps) {
  if (items.length <= 1) return null

  return (
    <div className="flex gap-1 overflow-x-auto">
      {items.map((item) => (
        <button
          key={item}
          onClick={() => onSelect(item)}
          className={`shrink-0 rounded px-2 py-0.5 font-mono text-xs ${
            active === item
              ? 'bg-neutral-200 text-neutral-900 dark:bg-neutral-800 dark:text-neutral-100'
              : 'text-neutral-500 hover:bg-neutral-100 dark:text-neutral-400 dark:hover:bg-neutral-900'
          }`}
        >
          {item}
        </button>
      ))}
    </div>
  )
}
