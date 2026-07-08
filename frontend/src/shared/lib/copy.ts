export async function copyText(value: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(value)
    return
  }

  const element = document.createElement('textarea')
  element.value = value
  element.setAttribute('readonly', 'true')
  element.style.position = 'fixed'
  element.style.opacity = '0'
  document.body.append(element)
  element.select()
  document.execCommand('copy')
  element.remove()
}
