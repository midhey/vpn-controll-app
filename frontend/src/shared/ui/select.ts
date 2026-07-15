export type SelectValue = string | number

export interface SelectOption {
  value: SelectValue
  label: string
  disabled?: boolean
}
