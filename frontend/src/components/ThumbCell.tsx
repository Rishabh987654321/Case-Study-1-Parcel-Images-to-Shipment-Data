import { getThumbnailUrl } from '../api/images'

export function ThumbCell({ imageId, name }: { imageId: string; name: string }) {
  return (
    <img
      src={getThumbnailUrl(imageId)}
      alt={name}
      loading="lazy"
      className="h-12 w-12 rounded border border-gray-200 bg-gray-50 object-cover"
    />
  )
}
