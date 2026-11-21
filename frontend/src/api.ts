import { z } from 'zod'

const capabilitySchema = z.object({
  id: z.string(),
  name: z.string(),
  status: z.enum(['available', 'planned']),
  description: z.string(),
})

const capabilitiesEnvelopeSchema = z.object({
  data: z.object({
    service: z.string(),
    version: z.string(),
    deploymentMode: z.string(),
    capabilities: z.array(capabilitySchema),
  }),
  meta: z.object({
    requestId: z.string(),
    timestamp: z.string(),
  }),
})

export type CapabilitiesEnvelope = z.infer<typeof capabilitiesEnvelopeSchema>

export async function fetchCapabilities(signal?: AbortSignal): Promise<CapabilitiesEnvelope> {
  const response = await fetch('/api/v1/system-catalog/capabilities', {
    headers: { Accept: 'application/json' },
    signal,
  })

  if (!response.ok) {
    throw new Error(`Capabilities request failed with status ${response.status}`)
  }

  return capabilitiesEnvelopeSchema.parse(await response.json())
}
