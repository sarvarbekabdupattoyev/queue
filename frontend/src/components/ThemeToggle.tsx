import { useTheme, type ThemeMode } from '../theme/ThemeContext'
import { IconLaptop, IconMoon, IconSun } from './icons'

const OPTIONS: { mode: ThemeMode; label: string; Icon: typeof IconSun }[] = [
  { mode: 'light', label: "Yorug' rejim", Icon: IconSun },
  { mode: 'system', label: 'Tizim rejimi', Icon: IconLaptop },
  { mode: 'dark', label: "Tungi rejim", Icon: IconMoon },
]

export function ThemeToggle() {
  const { mode, setMode } = useTheme()
  return (
    <div className="seg" role="group" aria-label="Mavzu">
      {OPTIONS.map(({ mode: value, label, Icon }) => (
        <button
          key={value}
          type="button"
          className={mode === value ? 'active' : ''}
          title={label}
          aria-label={label}
          aria-pressed={mode === value}
          onClick={() => setMode(value)}
        >
          <Icon size={15} />
        </button>
      ))}
    </div>
  )
}
