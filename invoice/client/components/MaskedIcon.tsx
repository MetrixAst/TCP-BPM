interface MaskedIconProps {
  icon: string
  className?: string
}

export default function MaskedIcon({ icon, className = '' }: MaskedIconProps) {
  return (
    <i
      className={`masked_icon ${className}`.trim()}
      style={{
        maskImage: `url(${icon})`,
        WebkitMaskImage: `url(${icon})`,
      }}
    />
  )
}
