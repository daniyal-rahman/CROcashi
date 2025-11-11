import { TimelineEvent } from '../api/client'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'

interface TimelineVisualizationProps {
  events: TimelineEvent[]
}

export default function TimelineVisualization({ events }: TimelineVisualizationProps) {
  // Group events by date and count by significance
  const eventCounts = events.reduce((acc, event) => {
    const date = event.event_date.split('T')[0]
    if (!acc[date]) {
      acc[date] = { date, critical: 0, major: 0, minor: 0, trace: 0 }
    }
    acc[date][event.event_significance] = (acc[date][event.event_significance] || 0) + 1
    return acc
  }, {} as Record<string, any>)

  const chartData = Object.values(eventCounts).sort((a: any, b: any) => 
    a.date.localeCompare(b.date)
  )

  return (
    <div className="bg-white rounded-lg shadow-md p-6 mb-6">
      <h3 className="text-xl font-bold mb-4">Event Timeline</h3>
      {chartData.length > 0 ? (
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="date" />
            <YAxis />
            <Tooltip />
            <Legend />
            <Line type="monotone" dataKey="critical" stroke="#ef4444" strokeWidth={2} />
            <Line type="monotone" dataKey="major" stroke="#f97316" strokeWidth={2} />
            <Line type="monotone" dataKey="minor" stroke="#f59e0b" strokeWidth={1} />
            <Line type="monotone" dataKey="trace" stroke="#6b7280" strokeWidth={1} />
          </LineChart>
        </ResponsiveContainer>
      ) : (
        <div className="text-center py-8 text-gray-500">No events to display</div>
      )}
      
      <div className="mt-4 space-y-2 max-h-64 overflow-y-auto">
        {events.slice(0, 20).map((event) => (
          <div key={event.event_id} className="flex items-start gap-3 p-2 hover:bg-gray-50 rounded">
            <div className={`w-2 h-2 rounded-full mt-2 ${
              event.event_significance === 'critical' ? 'bg-red-500' :
              event.event_significance === 'major' ? 'bg-orange-500' :
              event.event_significance === 'minor' ? 'bg-yellow-500' : 'bg-gray-400'
            }`} />
            <div className="flex-1">
              <div className="font-medium">{event.event_type}</div>
              <div className="text-sm text-gray-500">{event.event_date}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

